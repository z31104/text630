import cv2
import time
from flask import Blueprint, Response

from services.face_service import detect_face, recognize_face, draw_face_boxes, log_recognition_result, notify_vip_arrival

camera_bp = Blueprint("camera", __name__)

# 每 3 秒才重新做人臉辨識
last_recognition_time = 0

# 上一次辨識結果，給畫框顯示用
last_result = {
    "member_id": None,
    "name": "訪客",
    "vip": False,
    "line_id": None,
    "confidence": 0
}

# 記錄每個會員上一次產生 Recognition Log 的時間
# 格式範例：
# {
#     1: 1720000000.123,
#     2: 1720000030.456
# }
last_logged_times = {}


def generate_frames():
    global last_recognition_time, last_result, last_logged_times

    # 開啟攝影機
    # 0 通常代表筆電內建攝影機
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("無法開啟攝影機")
        return

    try:
        while True:
            success, frame = cap.read()

            if not success:
                break

            faces = detect_face(frame)
            current_time = time.time()

            # 每 3 秒才執行一次 dlib / face_recognition 會員比對
            if current_time - last_recognition_time >= 3:
                last_result = recognize_face(frame, faces)
                last_recognition_time = current_time

            # 每個會員 30 秒內不重複紀錄
            LOG_INTERVAL = 30

            # 信心值低於 0.6 的辨識結果先不記錄
            MIN_CONFIDENCE = 0.6

            current_member_id = last_result.get("member_id")
            current_confidence = last_result.get("confidence", 0)

            # 只記錄：
            # 1. 有辨識到會員 member_id
            # 2. confidence 達到最低門檻
            if current_member_id is not None and current_confidence >= MIN_CONFIDENCE:

                # 取得這位會員上一次被記錄的時間
                last_time = last_logged_times.get(current_member_id, 0)

                # 如果這位會員距離上次紀錄已經超過 30 秒，才印 Recognition Log
                if current_time - last_time >= LOG_INTERVAL:
                    log_recognition_result(last_result)
                    
                    # 如果是 VIP，模擬 VIP 到店通知
                    notify_vip_arrival(last_result)
                    
                    # 更新這位會員的最後紀錄時間
                    last_logged_times[current_member_id] = current_time

            # 畫框時直接使用上一筆辨識結果，不要再重新比對
            frame = draw_face_boxes(frame, faces, last_result)

            ret, buffer = cv2.imencode(".jpg", frame)

            if not ret:
                continue

            frame = buffer.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )

    finally:
        cap.release()


@camera_bp.route("/camera")
def camera():
    return """
    <h1>智慧會員辨識系統 - 攝影機畫面</h1>
    <p>即時攝影機串流</p>
    <img src="/camera/video_feed" width="640">
    """


@camera_bp.route("/camera/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )