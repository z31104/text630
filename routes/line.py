import os
from flask import Blueprint, request, abort

line_bp = Blueprint("line", __name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_ENABLED = bool(LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET)

if LINE_ENABLED:
    from linebot import LineBotApi, WebhookHandler
    from linebot.exceptions import InvalidSignatureError
    from linebot.models import FollowEvent, MessageEvent, TextMessage, TextSendMessage

    from linebot_service.notify import notify_new_friend

    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
else:
    line_bot_api = None
    handler = None
    print("警告：未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，LINE Bot 進入測試模式")


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
        # 加好友的瞬間，此時對方應為非會員，先推播一次通用歡迎訊息
        notify_new_friend(event.source.user_id)

    @handler.add(MessageEvent, message=TextMessage)
    def handle_message(event):
        # 先印出來，方便你確認有沒有收到訊息、順便記下自己的 userId
        print("收到訊息:", event.message.text)
        print("使用者 userId:", event.source.user_id)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=event.message.text)
        )
