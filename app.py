from dotenv import load_dotenv
load_dotenv()

from flask import Flask

from routes.home import home_bp
from routes.camera import camera_bp
from routes.member import member_bp
from routes.line import line_bp

app = Flask(__name__)

# 第三週新增：限制註冊照片最大 8 MB
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


app.register_blueprint(home_bp)
app.register_blueprint(camera_bp)
app.register_blueprint(member_bp)
app.register_blueprint(line_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)