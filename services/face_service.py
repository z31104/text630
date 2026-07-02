"""
AI 人臉偵測服務

目前版本：
- 使用 OpenCV Haar Cascade 做基本人臉偵測
- 偵測到人臉後回傳統一格式
- 尚未接資料庫，所以目前先統一回傳訪客資料

後續規劃：
- 接會員資料庫
- 加入會員人臉特徵比對
- 回傳會員 / VIP / 訪客辨識結果
"""

import cv2
from datetime import datetime

# 載入 OpenCV 內建的人臉偵測模型
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def detect_face(frame):
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


def recognize_face(faces):
    """
    根據偵測到的人臉，回傳統一格式的辨識結果。

    目前尚未接會員資料庫，所以：
    - 沒有辨識到會員時，統一回傳訪客
    - confidence 先給 0
    """

    if len(faces) == 0:
        return {
            "member_id": None,
            "name": "訪客",
            "vip": False,
            "line_id": None,
            "confidence": 0
        }

    return {
        "member_id": None,
        "name": "訪客",
        "vip": False,
        "line_id": None,
        "confidence": 0
    }


def draw_face_boxes(frame, faces):
    """
    在畫面上畫出人臉框框。
    frame: 攝影機畫面
    faces: 偵測到的人臉座標
    return: 畫好框框的 frame
    """

    result = recognize_face(faces)

    cv2.putText(
        frame,
        f"Name: {result['name']}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"VIP: {result['vip']}",
        (20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Confidence: {result['confidence']}",
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
            result["name"],
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

    return frame


def log_recognition_result(result):
    """
    將 AI 辨識結果印在終端機。
    欄位名稱依照組長統一格式：
    member_id, name, vip, line_id, confidence
    """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("========== Recognition Log ==========")
    print(f"Time: {now}")
    print(f"member_id: {result['member_id']}")
    print(f"name: {result['name']}")
    print(f"vip: {result['vip']}")
    print(f"line_id: {result['line_id']}")
    print(f"confidence: {result['confidence']}")
    print("=====================================")