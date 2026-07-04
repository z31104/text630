# from flask import Blueprint

# line_bp = Blueprint("line", __name__)

# @line_bp.route("/line")
# def line():
#     return """
#     <h1>LINE Bot 測試頁</h1>
#     <p>這裡之後接 LINE 通知功能</p>
#     """

import os
from flask import Blueprint, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import FollowEvent, MessageEvent, TextMessage, TextSendMessage

from linebot_service.notify import notify_new_friend

line_bp = Blueprint("line", __name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))


@line_bp.route("/line/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


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