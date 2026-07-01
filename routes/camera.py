import cv2
import time
from flask import Blueprint, Response

from services.face_service import detect_faces, draw_face_boxes, log_recognition_result

camera_bp = Blueprint("camera", __name__)

last_log_time = 0


def generate_frames():
    global last_log_time

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

            faces = detect_faces(frame)
            frame = draw_face_boxes(frame, faces)

            guest_count = len(faces)

            if guest_count > 0:
                status = "Guest Detected"
                guest_type = "Unknown Guest"
            else:
                status = "No Guest"
                guest_type = "None"

            current_time = time.time()

            # 每 3 秒印一次，避免終端機洗版
            if current_time - last_log_time >= 3:
                log_recognition_result(status, guest_count, guest_type)
                last_log_time = current_time

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


    