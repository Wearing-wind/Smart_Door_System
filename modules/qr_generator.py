"""
Smart Door Security System - QR Code Generator
Handles generating secure UUID tokens and Base64-encoded QR Code SVG images.
This module uses SvgPathImage to generate browser-compatible vector graphics.
"""

import io
import uuid
import base64
import qrcode
import qrcode.image.svg
import logging

logger = logging.getLogger(__name__)

def generate_secure_token() -> str:
    """
    Generate a cryptographically secure, random UUID token.
    No personal information is contained inside this token.
    """
    return str(uuid.uuid4())

def generate_qr_base64(token: str) -> str:
    """
    Generate a QR code image for the given token and return it as a Base64-encoded SVG string.
    
    Args:
        token: The secure token to encode.
        
    Returns:
        Base64-encoded SVG image string.
    """
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(token)
        qr.make(fit=True)

        # SvgPathImage generates standard, un-prefixed <path> SVG vector tags
        factory = qrcode.image.svg.SvgPathImage
        img = qr.make_image(image_factory=factory)
        
        # Save SVG to a byte stream
        buffered = io.BytesIO()
        img.save(buffered)
        
        # Convert bytes to base64 string
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return base64_str
    except Exception as e:
        logger.error(f"Error generating QR SVG Base64: {e}")
        return ""
