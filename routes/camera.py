import cv2
import time
from datetime import datetime
from flask import Blueprint, Response

from services.face_service import (
    detect_face,
    recognize_face,
    draw_face_boxes,
    log_recognition_result,
    send_line_notify
)

camera_bp = Blueprint("camera", __name__)

# 每 3 秒才重新做人臉辨識
last_recognition_time = 0

# 上一次辨識結果，給畫框顯示用
last_result = {
    "member_id": None,
    "name": "Guest",
    "phone": None,
    "vip": False,
    "member_level": "Guest",
    "visit_count": 0,
    "line_user_id": None,
    "total_amount": 0,
    "favorite_product": None,
    "face_image": None,
    "confidence": 0,
    "recognition_status": "Guest",
    "member_level_text": "陌生客"
}

# 記錄每個會員上一次產生 recognition log 的時間，避免同一個人一直寫入
last_logged_times = {}

# 記錄每個會員目前是否在店內，用來計算 visit_time / leave_time / stay_minutes
# 格式範例：
# {
#     1: {
#         "result": {...},
#         "visit_timestamp": 1720000000.123,
#         "visit_time": "2026-07-07 13:00:00",
#         "last_seen_timestamp": 1720000010.456
#     }
# }
active_visits = {}

# 訪客上一次產生 recognition log 的時間
last_guest_log_time = 0

# 設定參數
RECOGNITION_INTERVAL = 3       # 每 3 秒做一次人臉比對
MEMBER_LOG_INTERVAL = 30       # 同一會員每 30 秒最多記錄一次 recognition log
GUEST_LOG_INTERVAL = 60        # Guest 每 60 秒最多記錄一次，避免太頻繁
MIN_CONFIDENCE = 0.6           # 信心值低於 0.6 的會員辨識結果先不記錄
LEAVE_TIMEOUT = 60             # 超過 60 秒沒再看到同一會員，就先視為離店
CAMERA_ID = "camera_1"         # 對應 recognition_logs.camera_id


def now_text():
    """回傳目前時間文字，格式統一給 recognition_logs 使用。"""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def open_camera(camera_index=0):
    """
    開啟攝影機。

    函式名稱對齊專題規格：open_camera()
    攝影機編號設定
    0: 內建鏡頭，1: 外接 Logi C270 HD WebCam
    """

    CAMERA_INDEX = 1  
    cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
        print("無法開啟攝影機")
        return None

    return cap


def update_member_visit(result, current_time):
    """
    更新會員到店狀態。

    第一次看到會員：記錄 visit_time
    持續看到會員：更新 last_seen_timestamp
    """

    member_id = result.get("member_id")

    if member_id is None:
        return

    if member_id not in active_visits:
        visit_time = now_text()

        active_visits[member_id] = {
            "result": result,
            "visit_timestamp": current_time,
            "visit_time": visit_time,
            "last_seen_timestamp": current_time
        }

        # 到店開始紀錄，對應 recognition_logs.visit_status
        log_recognition_result(
            result,
            visit_time=visit_time,
            leave_time=None,
            stay_minutes=None,
            visit_status="visit_start",
            camera_id=CAMERA_ID
        )

        send_line_notify(result)

    else:
        active_visits[member_id]["result"] = result
        active_visits[member_id]["last_seen_timestamp"] = current_time


def close_timeout_visits(current_time):
    """
    檢查哪些會員已經超過 LEAVE_TIMEOUT 沒被拍到，
    先視為離店並計算 stay_minutes。
    """

    leaving_member_ids = []

    for member_id, visit_data in active_visits.items():
        last_seen = visit_data["last_seen_timestamp"]

        if current_time - last_seen >= LEAVE_TIMEOUT:
            leave_time = now_text()
            stay_seconds = current_time - visit_data["visit_timestamp"]
            stay_minutes = round(stay_seconds / 60, 2)

            log_recognition_result(
                visit_data["result"],
                visit_time=visit_data["visit_time"],
                leave_time=leave_time,
                stay_minutes=stay_minutes,
                visit_status="visit_end",
                camera_id=CAMERA_ID
            )

            leaving_member_ids.append(member_id)

    for member_id in leaving_member_ids:
        del active_visits[member_id]


def generate_frames():
    global last_recognition_time, last_result, last_logged_times, last_guest_log_time

    cap = open_camera(0)

    if cap is None:
        return

    try:
        while True:
            success, frame = cap.read()

            if not success:
                break

            faces = detect_face(frame)
            current_time = time.time()

            # 每 3 秒才執行一次 dlib / face_recognition 會員比對
            if current_time - last_recognition_time >= RECOGNITION_INTERVAL:
                last_result = recognize_face(frame, faces)
                last_recognition_time = current_time

            current_member_id = last_result.get("member_id")
            current_confidence = last_result.get("confidence", 0)
            has_face = len(faces) > 0

            # 會員紀錄：有 member_id 且信心值足夠，才當成正式會員紀錄
            if current_member_id is not None and current_confidence >= MIN_CONFIDENCE:
                update_member_visit(last_result, current_time)

                last_time = last_logged_times.get(current_member_id, 0)

                if current_time - last_time >= MEMBER_LOG_INTERVAL:
                    visit_time = active_visits[current_member_id]["visit_time"]

                    log_recognition_result(
                        last_result,
                        visit_time=visit_time,
                        leave_time=None,
                        stay_minutes=None,
                        visit_status="recognition",
                        camera_id=CAMERA_ID
                    )

                    last_logged_times[current_member_id] = current_time

            # Guest 紀錄：有偵測到臉，但沒有 member_id
            # MVP 階段不追蹤單一 Guest 身份，只做低頻率紀錄
            elif has_face and current_member_id is None:
                if current_time - last_guest_log_time >= GUEST_LOG_INTERVAL:
                    log_recognition_result(
                        last_result,
                        visit_time=now_text(),
                        leave_time=None,
                        stay_minutes=None,
                        visit_status="Guest_detected",
                        camera_id=CAMERA_ID
                    )

                    last_guest_log_time = current_time

            # 離店判斷：超過一段時間沒再看到同一會員，就先視為離店
            close_timeout_visits(current_time)

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
    <p>本週測試重點：一般會員 / VIP / Guest 辨識、到店時間、離店時間、停留時間</p>
    <img src="/camera/video_feed" width="640">
    """


@camera_bp.route("/camera/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
