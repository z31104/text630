"""
AI 人臉偵測服務

目前版本：
- 使用 OpenCV Haar Cascade 做基本人臉偵測
- 偵測到人臉後回傳統一格式
- 讀取 member_images 裡的會員假資料照片
- 尚未接資料庫，所以目前先統一回傳訪客資料

後續規劃：
- 使用 dlib 做會員人臉特徵比對
- 接會員資料庫
- 回傳會員 / VIP / 訪客辨識結果
"""

import os
from datetime import datetime

import cv2
import face_recognition

# 取得專案根目錄
# face_service.py 在 services 資料夾內，所以要往上一層回到專案根目錄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 會員假資料照片資料夾
MEMBER_IMAGE_DIR = os.path.join(BASE_DIR, "member_images")


def load_member_faces():
    """
    讀取 member_images 資料夾中的會員圖片，
    並使用 face_recognition 轉成人臉特徵資料。
    """

    members = []

    if not os.path.exists(MEMBER_IMAGE_DIR):
        print("找不到會員圖片資料夾:", MEMBER_IMAGE_DIR)
        return members

    for filename in os.listdir(MEMBER_IMAGE_DIR):
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            image_path = os.path.join(MEMBER_IMAGE_DIR, filename)

            # 讀取圖片
            image = face_recognition.load_image_file(image_path)

            # 取得圖片中的人臉特徵
            encodings = face_recognition.face_encodings(image)

            if len(encodings) == 0:
                print(f"會員圖片找不到人臉：{filename}")
                continue

            # 先取第一張臉
            face_encoding = encodings[0]

            # 目前先用檔名當會員 ID，例如 001.jpg -> 001
            member_id = os.path.splitext(filename)[0]

            members.append({
                "member_id": member_id,
                "name": f"Member {member_id}",
                "vip": False,
                "line_id": None,
                "encoding": face_encoding
            })

            print(f"已載入會員人臉：{filename}")

    print(f"會員人臉資料載入完成，共 {len(members)} 筆")
    return members


# 程式啟動時先讀取會員圖片
known_members = load_member_faces()


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

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60)
    )

    return faces


def recognize_face(frame, faces):
    """
    使用 face_recognition 比對攝影機畫面中的人臉是否為會員。

    frame: 攝影機畫面
    faces: OpenCV 偵測到的人臉座標
    return: 辨識結果
    """

    if len(faces) == 0:
        return {
            "member_id": None,
            "name": "訪客",
            "vip": False,
            "line_id": None,
            "confidence": 0
        }

    # OpenCV 的顏色格式是 BGR
    # face_recognition 需要 RGB，所以要轉換
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 目前先只比對第一張偵測到的人臉
    x, y, w, h = faces[0]

    # OpenCV 座標格式是 x, y, w, h
    # face_recognition 座標格式是 top, right, bottom, left
    face_location = (y, x + w, y + h, x)

    # 將攝影機中的人臉轉成特徵值
    encodings = face_recognition.face_encodings(rgb_frame, [face_location])

    if len(encodings) == 0:
        return {
            "member_id": None,
            "name": "訪客",
            "vip": False,
            "line_id": None,
            "confidence": 0
        }

    current_encoding = encodings[0]

    # 逐一和已載入的會員人臉資料比對
    for member in known_members:
        distance = face_recognition.face_distance(
            [member["encoding"]],
            current_encoding
        )[0]

        # distance 越小代表越像
        # 一般可先用 0.6 當門檻
        confidence = round(1 - distance, 2)

        if distance < 0.6:
            return {
                "member_id": member["member_id"],
                "name": member["name"],
                "vip": member["vip"],
                "line_id": member["line_id"],
                "confidence": confidence
            }

    # 沒有比對成功就回傳訪客
    return {
        "member_id": None,
        "name": "訪客",
        "vip": False,
        "line_id": None,
        "confidence": 0
    }


def draw_face_boxes(frame, faces, result=None):
    """
    在畫面上畫出人臉框框。
    frame: 攝影機畫面
    faces: 偵測到的人臉座標
    result: 辨識結果，若沒有傳入才重新辨識
    return: 畫好框框的 frame
    """

    if result is None:
        result = recognize_face(frame, faces)

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