from flask import Blueprint

home_bp = Blueprint("home", __name__)

@home_bp.route("/")
def home():
    return """
    <h1>智慧會員辨識系統</h1>
    <p>系統啟動成功</p>
    """