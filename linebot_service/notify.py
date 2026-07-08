import os
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from linebot.models import TextSendMessage

# 延後初始化 LineBotApi：若環境變數未設定，將停用 LINE 推播而不造成例外
# 顧客用 LINE 官方帳號
_LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
if not _LINE_CHANNEL_ACCESS_TOKEN:
    line_bot_api = None
    print("警告：未設定 LINE_CHANNEL_ACCESS_TOKEN，LINE 推播功能已停用")
else:
    line_bot_api = LineBotApi(_LINE_CHANNEL_ACCESS_TOKEN)

# 店員用 LINE 官方帳號，固定推播給 STAFF_LINE_USER_ID（VIP 到店通知用）
_STAFF_LINE_CHANNEL_ACCESS_TOKEN = os.getenv("STAFF_LINE_CHANNEL_ACCESS_TOKEN")
STAFF_LINE_USER_ID = os.getenv("STAFF_LINE_USER_ID")
if not _STAFF_LINE_CHANNEL_ACCESS_TOKEN:
    staff_line_bot_api = None
    print("警告：未設定 STAFF_LINE_CHANNEL_ACCESS_TOKEN，店員 LINE 推播功能已停用")
else:
    staff_line_bot_api = LineBotApi(_STAFF_LINE_CHANNEL_ACCESS_TOKEN)


def push_message(line_user_id, text):
    """
    顧客 Bot 的底層推播函式，其他推播給「會員本人」的 notify_* 函式都透過這裡發送。
    失敗時不往外丟例外，避免打斷呼叫端（例如攝影機辨識迴圈）。
    return: "sent" 或 "failed"
    """
    if not line_user_id:
        print("推播失敗：沒有 line_user_id")
        return "failed"

    if line_bot_api is None:
        print("推播失敗：LINE Channel Access Token 未設定，已停用推播功能")
        return "failed"

    try:
        line_bot_api.push_message(line_user_id, TextSendMessage(text=text))
        return "sent"
    except LineBotApiError as e:
        print(f"LINE 推播失敗：{e}")
        return "failed"


def push_staff_message(text):
    """
    店員 Bot 的底層推播函式，固定推給 STAFF_LINE_USER_ID。
    return: "sent" 或 "failed"
    """
    if not STAFF_LINE_USER_ID:
        print("推播失敗：未設定 STAFF_LINE_USER_ID")
        return "failed"

    if staff_line_bot_api is None:
        print("推播失敗：STAFF_LINE_CHANNEL_ACCESS_TOKEN 未設定，已停用店員推播功能")
        return "failed"

    try:
        staff_line_bot_api.push_message(STAFF_LINE_USER_ID, TextSendMessage(text=text))
        return "sent"
    except LineBotApiError as e:
        print(f"店員 LINE 推播失敗：{e}")
        return "failed"


def notify_vip_recognition(data):
    """
    觸發時機①：人臉辨識掃到 VIP 會員時呼叫（由 face_service.py 呼叫）。
    這則通知是給「店員」看的，所以固定推到店員 Bot（STAFF_LINE_USER_ID），
    不是推給會員自己的 line_user_id。
    data 格式範例：
    {
        "member_id": 1,
        "name": "王小明",
        "vip": True,
        "line_user_id": "U123456789",
        "confidence": 0.95
    }
    """
    if not data.get("vip"):
        return None

    name = data.get("name")
    message = f"VIP會員 {name} 到店了！"
    return push_staff_message(message)


def notify_vip_upgrade(member):
    """
    觸發時機②：會員資料庫的 vip 從 false 變 true 時呼叫（由 routes/member.py 呼叫）。
    member 格式範例：
    {
        "member_id": 1,
        "name": "王小明",
        "line_user_id": "U123456789"
    }
    """
    line_user_id = member.get("line_user_id")
    name = member.get("name")

    if not line_user_id:
        return None

    message = f"恭喜 {name}，您已成功升級為 VIP 會員！"
    return push_message(line_user_id, message)


def notify_new_friend(line_user_id):
    """
    觸發時機③：使用者加入 LINE 好友的瞬間呼叫（此時應為非會員，由 routes/line.py 呼叫）。
    """
    if not line_user_id:
        return None

    message = "感謝加入好友！歡迎申請成為會員，即可享有 VIP 專屬通知服務。"
    return push_message(line_user_id, message)
