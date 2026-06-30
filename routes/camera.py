import cv2
from flask import Blueprint, Response

camera_bp = Blueprint("camera", __name__)

# 開啟攝影機
# 0 通常代表筆電內建攝影機
cap = cv2.VideoCapture(0)


def generate_frames():
    while True:
        success, frame = cap.read()

        if not success:
            break

        # 把畫面轉成 JPG
        ret, buffer = cv2.imencode(".jpg", frame)

        if not ret:
            continue

        frame = buffer.tobytes()

        # 串流給網頁
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )


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