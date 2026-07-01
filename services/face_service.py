"""
AI 人臉偵測服務

目前版本：
- 使用 OpenCV Haar Cascade 做基本人臉偵測
- 偵測到人臉後回傳座標
- 由 camera.py 負責呼叫並顯示框線

後續規劃：
- 若 dlib 環境確認完成，可將偵測與辨識邏輯升級為 dlib
- 加入會員人臉特徵比對
- 回傳會員 / VIP / 陌生人辨識結果
"""

import cv2
from datetime import datetime

# 載入 OpenCV 內建的人臉偵測模型
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def detect_faces(frame):
    """
    偵測畫面中的人臉，並回傳人臉座標。
    frame: 攝影機讀到的原始畫面
    return: faces
    """

    # 轉成灰階，讓 OpenCV 比較容易偵測人臉
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 偵測人臉
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60)
    )

    return faces

def recognize_guest(faces):
    """
    根據偵測到的人臉數量，回傳目前辨識狀態。
    目前先以 Unknown Guest 模擬陌生顧客。
    未來可改成會員 / VIP / 陌生熟客辨識。
    """

    face_count = len(faces)

    if face_count == 0:
        return {
            "status": "no_face",
            "person_type": "None",
            "name": None,
            "face_count": 0,
            "message": "No Guest"
        }

    return {
        "status": "guest",
        "person_type": "Unknown Guest",
        "name": "Guest",
        "face_count": face_count,
        "message": "Guest Detected"
    }

def draw_face_boxes(frame, faces):
    """
    在畫面上畫出人臉框框。
    frame: 攝影機畫面
    faces: 偵測到的人臉座標
    return: 畫好框框的 frame
    """

    result = recognize_guest(faces)

    cv2.putText(
        frame,
        f"Status: {result['message']}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Guests: {result['face_count']}",
        (20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Type: {result['person_type']}",
        (20, 110),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.putText(
            frame,
            "Guest Detected",
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

    return frame

def log_recognition_result(status, guest_count, guest_type):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("========== Recognition Log ==========")
    print(f"Time: {now}")
    print(f"Status: {status}")
    print(f"Guests: {guest_count}")
    print(f"Type: {guest_type}")
    print("=====================================")