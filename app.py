from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request

from routes.home import home_bp
from routes.camera import camera_bp
from routes.member import member_bp
from routes.line import line_bp

app = Flask(__name__)

# 註冊照片本身限制 8 MB；multipart 還包含欄位與封包邊界，
# 因此 Flask 的整體 request 上限需保留額外空間。
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


app.register_blueprint(home_bp)
app.register_blueprint(camera_bp)
app.register_blueprint(member_bp)
app.register_blueprint(line_bp)


@app.errorhandler(413)
def request_too_large(error):
    if request.path == "/line/register":
        return jsonify({
            "success": False,
            "message": "照片大小不可超過 8 MB，請縮小照片後再試。",
        }), 413

    return "上傳內容過大", 413


@app.errorhandler(500)
def internal_server_error(error):
    if request.path == "/line/register":
        return jsonify({
            "success": False,
            "message": "會員註冊暫時失敗，請稍後再試。",
        }), 500

    return "伺服器內部錯誤", 500

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
