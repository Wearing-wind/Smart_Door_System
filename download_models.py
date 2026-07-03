import urllib.request
import os

print("Downloading YuNet...")
urllib.request.urlretrieve(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "yunet.onnx"
)
print("Downloading SFace...")
urllib.request.urlretrieve(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "sface.onnx"
)
print("Done!")
