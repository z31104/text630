from flask import Blueprint

member_bp = Blueprint("member", __name__)

@member_bp.route("/member")
def member():
    return """
    <h1>會員資料頁</h1>
    <p>這裡之後接 MySQL / SQLite 會員資料</p>
    """