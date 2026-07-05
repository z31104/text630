from flask import Flask
from dotenv import load_dotenv
load_dotenv()

from routes.line import line_bp

app = Flask(__name__)
app.register_blueprint(line_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)