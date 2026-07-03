import os
from linebot import LineBotApi
from linebot.models import TextSendMessage

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))


def send_line_notify(data):
    """
    data 是 AI 組傳來的辨識結果，格式範例：
    {
        "member_id": 1,
        "name": "王小明",
        "vip": true,
        "line_id": "U123456789",
        "confidence": 0.95
    }
    """
    if not data.get("vip"):
        return  # 不是 VIP，不用通知

    line_id = data.get("line_id")
    name = data.get("name")

    if not line_id:
        return  # 沒有 line_id 沒辦法推播

    message = f"VIP會員 {name} 到店了！"
    line_bot_api.push_message(line_id, TextSendMessage(text=message))