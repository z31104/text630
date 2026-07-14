import os
import uuid
from flask import Blueprint, request, abort, jsonify

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FollowEvent, MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, URIAction,
)

from database.db import get_connection, insert_member
from linebot_service.notify import push_message
from services.face_service import (
    validate_member_face_image,
    register_member_face,
    MEMBER_IMAGE_DIR,
)

ALLOWED_FACE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

line_bp = Blueprint("line", __name__)

REGISTER_KEYWORDS = {"註冊", "會員", "加入會員", "register"}

# 顧客用 LINE 官方帳號
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_ENABLED = bool(LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET)

if LINE_ENABLED:
    from linebot_service.notify import notify_new_friend

    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
else:
    line_bot_api = None
    handler = None
    print("警告：未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，LINE Bot 進入測試模式")

# 店員用 LINE 官方帳號，用來接收 VIP 到店通知
STAFF_LINE_CHANNEL_ACCESS_TOKEN = os.getenv("STAFF_LINE_CHANNEL_ACCESS_TOKEN")
STAFF_LINE_CHANNEL_SECRET = os.getenv("STAFF_LINE_CHANNEL_SECRET")
STAFF_LINE_ENABLED = bool(STAFF_LINE_CHANNEL_ACCESS_TOKEN and STAFF_LINE_CHANNEL_SECRET)

if STAFF_LINE_ENABLED:
    staff_line_bot_api = LineBotApi(STAFF_LINE_CHANNEL_ACCESS_TOKEN)
    staff_handler = WebhookHandler(STAFF_LINE_CHANNEL_SECRET)
else:
    staff_line_bot_api = None
    staff_handler = None
    print("警告：未設定 STAFF_LINE_CHANNEL_ACCESS_TOKEN / STAFF_LINE_CHANNEL_SECRET，店員 LINE Bot 進入測試模式")


def get_registration_link(line_user_id):
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = request.url_root.rstrip("/")
        if base_url.startswith("http://"):
            # ngrok 對外一定是 https，但轉送到本機 Flask 時是用 http，
            # 這裡把 scheme 校正成 https，否則 LINE 會拒絕整則按鈕訊息
            base_url = "https://" + base_url[len("http://"):]
    return f"{base_url}/register?line_user_id={line_user_id}"


def build_register_message(line_user_id):
    link = get_registration_link(line_user_id)
    return TemplateSendMessage(
        alt_text="立即完成會員註冊，領取新會員禮！",
        template=ButtonsTemplate(
            title="歡迎加入！",
            text="完成會員註冊即可領取新會員禮與抽獎機會",
            actions=[
                URIAction(label="立即註冊會員", uri=link)
            ]
        )
    )


@line_bp.route("/line")
def line_index():
    if not LINE_ENABLED:
        return """
        <h1>LINE Bot - 測試模式</h1>
        <p>未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，目前為測試模式</p>
        """
    return """
    <h1>LINE Bot - 正式模式</h1>
    <p>已偵測到 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，LINE Bot 已啟動</p>
    """


@line_bp.route("/line/callback", methods=["POST"])
def callback():
    if not LINE_ENABLED:
        return "OK (test mode)"

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


if LINE_ENABLED:
    @handler.add(FollowEvent)
    def handle_follow(event):
        user_id = event.source.user_id

        # 加好友的瞬間，此時對方應為非會員，先推播一次通用歡迎訊息，
        # 再接著推播一則帶有註冊連結的按鈕訊息
        notify_new_friend(user_id)
        line_bot_api.push_message(user_id, build_register_message(user_id))

    @handler.add(MessageEvent, message=TextMessage)
    def handle_message(event):
        user_id = event.source.user_id
        text = event.message.text.strip()

        # 先印出來，方便你確認有沒有收到訊息、順便記下自己的 userId
        print("收到訊息:", text)
        print("使用者 userId:", user_id)

        if text in REGISTER_KEYWORDS:
            line_bot_api.reply_message(event.reply_token, build_register_message(user_id))
            return

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=event.message.text)
        )


@line_bp.route("/line/staff/callback", methods=["POST"])
def staff_callback():
    if not STAFF_LINE_ENABLED:
        return "OK (staff test mode)"

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        staff_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


if STAFF_LINE_ENABLED:
    @staff_handler.add(FollowEvent)
    def handle_staff_follow(event):
        print("店員 Bot 加好友，userId:", event.source.user_id)

    @staff_handler.add(MessageEvent, message=TextMessage)
    def handle_staff_message(event):
        # 這裡的目的只是為了讓你能在後台 log 看到店員自己的 userId
        print("店員 Bot 收到訊息:", event.message.text)
        print("店員 userId:", event.source.user_id)

        staff_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已收到，你的 userId 是：{event.source.user_id}")
        )


def _fetch_member_by_line_user_id(line_user_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id, name, phone, vip, member_level, visit_count, "
            "line_user_id, total_amount, favorite_product, face_image, created_at, updated_at "
            "FROM members WHERE line_user_id = %s",
            (line_user_id,)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _fetch_member_by_id(member_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id, name, phone, vip, member_level, visit_count, "
            "line_user_id, total_amount, favorite_product, face_image, created_at, updated_at "
            "FROM members WHERE member_id = %s",
            (member_id,)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _delete_member(member_id):
    """人臉建檔失敗時，把已建立的會員資料整筆撤銷，避免留下沒有照片的殘缺會員。"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM face_images WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM members WHERE member_id = %s", (member_id,))
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"撤銷會員（member_id={member_id}）失敗：", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@line_bp.route("/line/register", methods=["POST"])
def register_from_line():
    """
    LINE 會員註冊 API（LINE 組自己的端點，只用 database.db 既有的 get_connection）。
    line_user_id 是使用者透過 LIFF 登入後，由前端 register.js 呼叫 liff.getProfile() 取得的。

    第三週改版：改收 multipart/form-data，新會員必須附上 face_image 照片才能完成人臉建檔，
    照片只要沒偵測到人臉、偵測到多張臉、或建檔失敗，整筆註冊都會撤銷（不留殘缺會員資料）。
    """
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    line_user_id = (request.form.get("line_user_id") or "").strip() or None
    face_image_file = request.files.get("face_image")

    if not name:
        return jsonify({"error": "請輸入姓名"}), 400

    if not line_user_id:
        return jsonify({"error": "缺少 LINE 使用者資訊，請從 LINE 官方帳號的註冊連結進入此頁面"}), 400

    try:
        member = _fetch_member_by_line_user_id(line_user_id)
    except Exception as e:
        print("會員查詢失敗：", e)
        return jsonify({"error": "註冊失敗，請稍後再試", "detail": str(e)}), 500

    if member is not None:
        return jsonify({
            "message": "您已經是會員囉，這是您目前的會員資料",
            "is_new": False,
            "member": member,
        })

    if not face_image_file or not face_image_file.filename:
        return jsonify({"error": "請上傳您的照片以完成人臉建檔"}), 400

    ext = os.path.splitext(face_image_file.filename)[1].lower()
    if ext not in ALLOWED_FACE_IMAGE_EXTENSIONS:
        return jsonify({"error": "照片格式不支援，請上傳 jpg 或 png 檔"}), 400

    os.makedirs(MEMBER_IMAGE_DIR, exist_ok=True)
    saved_filename = f"line_{uuid.uuid4().hex}{ext}"
    image_path = os.path.join(MEMBER_IMAGE_DIR, saved_filename)
    face_image_file.save(image_path)

    face_check = validate_member_face_image(image_path)
    if not face_check.get("success"):
        os.remove(image_path)
        return jsonify({"error": face_check.get("message", "照片驗證失敗")}), 400

    try:
        member_id = insert_member(
            name=name,
            phone=phone,
            member_level="normal",
            line_user_id=line_user_id,
            face_image=saved_filename,
            registration_source="line",
        )
    except Exception as e:
        os.remove(image_path)
        print("會員註冊失敗：", e)
        return jsonify({"error": "註冊失敗，請稍後再試", "detail": str(e)}), 500

    face_result = register_member_face(member_id, image_path)
    if not face_result.get("success"):
        _delete_member(member_id)
        os.remove(image_path)
        return jsonify({"error": face_result.get("message", "人臉建檔失敗")}), 500

    member = _fetch_member_by_id(member_id)

    push_message(
        line_user_id,
        f"{name} 您好，歡迎加入會員！記得下次到店讓我們認出您 😊"
    )

    return jsonify({
        "message": "註冊成功",
        "is_new": True,
        "member": member,
    })
