from dotenv import load_dotenv
load_dotenv()

from flask import Flask

from routes.home import home_bp
from routes.camera import camera_bp
from routes.member import member_bp
from routes.line import line_bp

app = Flask(__name__)

app.register_blueprint(home_bp)
app.register_blueprint(camera_bp)
app.register_blueprint(member_bp)
app.register_blueprint(line_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)