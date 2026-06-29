from flask import Blueprint

line_bp = Blueprint("line", __name__)

@line_bp.route("/line")
def line():
    return """
    <h1>LINE Bot 測試頁</h1>
    <p>這裡之後接 LINE 通知功能</p>
    """