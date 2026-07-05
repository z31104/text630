import os
from dotenv import load_dotenv
load_dotenv()

from linebot import LineBotApi
from linebot.models import TextSendMessage

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))

# 把下面換成你剛剛複製的 userId
my_user_id = "U0e1d13231946c4c52e179049463c6b49"

line_bot_api.push_message(
    my_user_id,
    TextSendMessage(text="這是測試推播訊息！")
)

print("推播完成")