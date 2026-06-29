from flask import Blueprint

camera_bp = Blueprint("camera", __name__)

@camera_bp.route("/camera")
def camera():
    return """
    <h1>攝影機頁面</h1>
    <p>這裡之後放 OpenCV 攝影機功能</p>
    """