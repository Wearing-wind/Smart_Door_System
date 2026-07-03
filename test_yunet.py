import cv2
import numpy as np
import os

class _FaceRecognitionFallback:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        yunet_path = os.path.join(base_dir, "yunet.onnx")
        sface_path = os.path.join(base_dir, "sface.onnx")
        
        self.detector = cv2.FaceDetectorYN_create(yunet_path, "", (320, 320))
        self.recognizer = cv2.FaceRecognizerSF_create(sface_path, "")
        
    def face_locations(self, img, model="hog"):
        height, width, _ = img.shape
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(img)
        locations = []
        if faces is not None:
            for face in faces:
                x, y, w, h = map(int, face[:4])
                # Return (top, right, bottom, left)
                locations.append((y, x+w, y+h, x))
        return locations
        
    def face_encodings(self, img, known_face_locations=None, num_jitters=1, model="small"):
        height, width, _ = img.shape
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(img)
        
        encodings = []
        if faces is not None:
            for face in faces:
                # Optionally match to known_face_locations here
                # but for simplicity, we can just encode all detected faces
                # If known_face_locations is given, we find the closest match
                if known_face_locations is not None:
                    x, y, w, h = map(int, face[:4])
                    top, right, bottom, left = y, x+w, y+h, x
                    matched = False
                    for (k_top, k_right, k_bottom, k_left) in known_face_locations:
                        # Check intersection
                        if (k_left < right and k_right > left and
                            k_top < bottom and k_bottom > top):
                            matched = True
                            break
                    if not matched:
                        continue
                
                # Align and extract features
                face_align = self.recognizer.alignCrop(img, face)
                feature = self.recognizer.feature(face_align)
                encodings.append(feature[0].flatten())
        return encodings
        
    def face_distance(self, face_encodings, face_to_compare):
        if len(face_encodings) == 0:
            return np.empty((0,))
        # Euclidean distance
        return np.linalg.norm(np.array(face_encodings) - face_to_compare, axis=1)

if __name__ == '__main__':
    fallback = _FaceRecognitionFallback()
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    locs = fallback.face_locations(img)
    print("Locations:", locs)
