import os
from flask import Blueprint, request, abort, jsonify

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FollowEvent, MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, URIAction,
)

from database.db import get_connection
from linebot_service.notify import push_message

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


@line_bp.route("/line/register", methods=["POST"])
def register_from_line():
    """
    LINE 會員註冊 API（LINE 組自己的端點，只用 database.db 既有的 get_connection）。
    line_user_id 是使用者透過 LIFF 登入後，由前端 register.js 呼叫 liff.getProfile() 取得的。
    """
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    line_user_id = (data.get("line_user_id") or "").strip() or None

    if not name:
        return jsonify({"error": "請輸入姓名"}), 400

    if not line_user_id:
        return jsonify({"error": "缺少 LINE 使用者資訊，請從 LINE 官方帳號的註冊連結進入此頁面"}), 400

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
        member = cursor.fetchone()
        is_new = member is None

        if is_new:
            cursor.execute(
                "INSERT INTO members (name, phone, vip, member_level, visit_count, line_user_id, total_amount) "
                "VALUES (%s, %s, FALSE, '一般會員', 0, %s, 0)",
                (name, phone, line_user_id)
            )
            conn.commit()

            cursor.execute(
                "SELECT member_id, name, phone, vip, member_level, visit_count, "
                "line_user_id, total_amount, favorite_product, face_image, created_at, updated_at "
                "FROM members WHERE member_id = %s",
                (cursor.lastrowid,)
            )
            member = cursor.fetchone()

    except Exception as e:
        if conn:
            conn.rollback()
        print("會員註冊失敗：", e)
        return jsonify({"error": "註冊失敗，請稍後再試", "detail": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if is_new:
        push_message(
            line_user_id,
            f"{name} 您好，歡迎加入會員！記得下次到店讓我們認出您 😊"
        )

    return jsonify({
        "message": "註冊成功" if is_new else "您已經是會員囉，這是您目前的會員資料",
        "is_new": is_new,
        "member": member,
    })
