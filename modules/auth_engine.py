"""
Smart Door Security System - Authentication Engine
Supports face-only authentication mode.
"""

import threading
import logging
import time
from typing import Optional, Callable, Tuple
from enum import Enum
from dataclasses import dataclass, field
import sys
from pathlib import Path
import queue
import weakref
from collections import deque
import gc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import AUTH_TIMEOUT
from database.db_manager import AccessLogRepository, UserRepository, SystemLogRepository

from modules.face_recognition_module import (
    FaceRecognitionEngine, FaceResult, FaceStatus
)
from modules.door_control import DoorController, DoorState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AuthState(Enum):
    """Authentication state machine states."""
    IDLE = "Waiting for Authentication"
    FACE_PENDING = "Face Verification Pending"
    FACE_MATCHED = "Face Verified"
    VERIFYING = "Verifying Identity..."
    ACCESS_GRANTED = "ACCESS GRANTED"
    ACCESS_DENIED = "ACCESS DENIED"
    TIMEOUT = "Authentication Timeout"
    ERROR = "Authentication Error"


@dataclass
class AuthSession:
    """Represents an authentication session."""
    state: AuthState = AuthState.IDLE
    face_result: Optional[FaceResult] = None
    face_user_id: Optional[int] = None
    matched_user_id: Optional[int] = None
    matched_user_name: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    failure_reason: Optional[str] = None
    confidence: float = 0.0
    auth_method: str = "face"


class AuthenticationEngine:
    """
    Face-only authentication engine.
    """
    
    def __init__(self, simulation: bool = False):
        self.simulation = simulation
        self.auth_mode = "face"
        
        self.face_engine = FaceRecognitionEngine()
        self.door_controller = DoorController(simulation=simulation)
        
        self.access_log = AccessLogRepository()
        self.user_repo = UserRepository()
        self.system_log = SystemLogRepository()
        
        self._current_session: Optional[AuthSession] = None
        self._session_lock = threading.Lock()
        self._running = False
        self._auth_thread: Optional[threading.Thread] = None
        
        self._state_callbacks: list = []
        self._result_callbacks: list = []
        
        self.auth_timeout = AUTH_TIMEOUT
    
    def add_state_callback(self, callback: Callable[[AuthSession], None]):
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)
    
    def remove_state_callback(self, callback: Callable[[AuthSession], None]):
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
    
    def add_result_callback(self, callback: Callable[[AuthSession], None]):
        if callback not in self._result_callbacks:
            self._result_callbacks.append(callback)
    
    def _notify_state_change(self, session: AuthSession):
        for callback in self._state_callbacks:
            try:
                callback(session)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def _notify_result(self, session: AuthSession):
        for callback in self._result_callbacks:
            try:
                callback(session)
            except Exception as e:
                logger.error(f"Result callback error: {e}")
    
    def start(self) -> bool:
        logger.info("Starting authentication engine (mode=face)...")
        
        if not self.face_engine.start():
            logger.error("Failed to start face recognition")
            self.system_log.error("AuthEngine", "Failed to start face recognition")
            return False
        
        self._running = True
        self._current_session = AuthSession()
        
        self._auth_thread = threading.Thread(target=self._auth_loop, daemon=True)
        self._auth_thread.start()
        
        logger.info("Authentication engine started (mode=face)")
        self.system_log.info("AuthEngine", "Authentication engine started (mode=face)")
        return True
    
    def stop(self):
        self._running = False
        if self._auth_thread:
            self._auth_thread.join(timeout=3.0)
        
        self.face_engine.stop()
        self.door_controller.cleanup()
        
        logger.info("Authentication engine stopped")
        self.system_log.info("AuthEngine", "Authentication engine stopped")
    
    def _auth_loop(self):
        while self._running:
            try:
                with self._session_lock:
                    if self._current_session is None:
                        self._current_session = AuthSession()
                    session = self._current_session
                
                if session.state not in [AuthState.IDLE, AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED]:
                    elapsed = time.time() - session.start_time
                    if elapsed > self.auth_timeout:
                        self._handle_timeout(session)
                        continue
                
                if session.state == AuthState.IDLE:
                    self._process_idle_state(session)
                elif session.state in (AuthState.FACE_MATCHED,):
                    self._process_verification(session)
                elif session.state in [AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED]:
                    time.sleep(3)
                    self._reset_session()
                
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Auth loop error: {e}")
                self.system_log.error("AuthEngine", f"Auth loop error: {str(e)}")
                time.sleep(1)
    
    def _process_idle_state(self, session: AuthSession):
        face_result = self.face_engine.process_frame()
        
        if face_result.status == FaceStatus.FACE_MATCHED:
            user = self.user_repo.get_by_id(face_result.user_id)
            if user and user.get('is_active', False):
                session.state = AuthState.FACE_MATCHED
                session.face_result = face_result
                session.face_user_id = face_result.user_id
                session.start_time = time.time()
                session.auth_method = "face"
                logger.info(f"Face matched: {face_result.user_name}")
                self._notify_state_change(session)
            else:
                logger.warning(f"Face matched but user inactive: {face_result.user_name}")
    
    def _process_verification(self, session: AuthSession):
        self._process_face_only(session)
    
    def _process_face_only(self, session: AuthSession):
        if session.state == AuthState.FACE_MATCHED:
            user = self.user_repo.get_by_id(session.face_user_id)
            if user and user.get('is_active', False):
                self._grant_access(session, user)
            else:
                self._deny_access(session, "User account is disabled")
    
    def _grant_access(self, session: AuthSession, user: dict):
        session.state = AuthState.ACCESS_GRANTED
        session.matched_user_id = user['id']
        session.matched_user_name = f"{user['first_name']} {user['last_name']}"
        session.end_time = time.time()
        
        scores = []
        if session.face_result:
            scores.append(session.face_result.confidence)
        session.confidence = sum(scores) / len(scores) if scores else 0
        
        self.door_controller.unlock(
            reason=f"Authenticated: {session.matched_user_name}"
        )
        
        self.access_log.log_access(
            user_id=session.matched_user_id,
            event_type='ENTRY',
            result='SUCCESS',
            face_match=True,
            confidence_score=session.confidence
        )
        
        logger.info(f"ACCESS GRANTED: {session.matched_user_name}")
        self.system_log.info(
            "AuthEngine",
            f"Access granted to {session.matched_user_name}",
            f"Confidence: {session.confidence:.2f}"
        )
        
        self._notify_state_change(session)
        self._notify_result(session)
    
    def _deny_access(self, session: AuthSession, reason: str):
        session.state = AuthState.ACCESS_DENIED
        session.failure_reason = reason
        session.end_time = time.time()
        
        self.door_controller.lock(reason="Access denied")
        
        face_match = (session.face_result is not None and
                      session.face_result.status == FaceStatus.FACE_MATCHED)
        
        self.access_log.log_access(
            user_id=session.face_user_id,
            event_type='ENTRY',
            result='DENIED',
            face_match=face_match,
            failure_reason=reason
        )
        
        logger.warning(f"ACCESS DENIED: {reason}")
        self.system_log.warning("AuthEngine", f"Access denied: {reason}")
        
        self._notify_state_change(session)
        self._notify_result(session)
    
    def _handle_timeout(self, session: AuthSession):
        session.state = AuthState.TIMEOUT
        session.failure_reason = "Authentication timeout"
        session.end_time = time.time()
        
        face_match = (session.face_result is not None and
                      session.face_result.status == FaceStatus.FACE_MATCHED)
        
        self.access_log.log_access(
            user_id=session.face_user_id,
            event_type='ENTRY',
            result='FAILED',
            face_match=face_match,
            failure_reason="Timeout"
        )
        
        logger.warning("Authentication timeout")
        self.system_log.warning("AuthEngine", "Authentication timeout")
        
        self._notify_state_change(session)
        self._notify_result(session)
        time.sleep(2)
        self._reset_session()
    
    def _reset_session(self):
        with self._session_lock:
            self._current_session = AuthSession()
            self._notify_state_change(self._current_session)
    
    def get_current_session(self) -> AuthSession:
        with self._session_lock:
            if self._current_session is None:
                self._current_session = AuthSession()
            return self._current_session
    
    def get_face_frame(self):
        return self.face_engine.get_current_frame()
    
    def process_face(self) -> FaceResult:
        return self.face_engine.process_frame()
    
    def cancel_authentication(self):
        with self._session_lock:
            if self._current_session and self._current_session.state not in [
                AuthState.IDLE, AuthState.ACCESS_GRANTED, AuthState.ACCESS_DENIED
            ]:
                self._current_session.state = AuthState.ACCESS_DENIED
                self._current_session.failure_reason = "Cancelled"
                self._notify_state_change(self._current_session)
        self._reset_session()


def get_auth_engine(simulation: bool = False) -> AuthenticationEngine:
    return AuthenticationEngine(simulation=simulation)
