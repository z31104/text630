from dotenv import load_dotenv
load_dotenv()

from notify import notify_vip_recognition

# 假資料：模擬攝影機辨識到一位 VIP 會員
fake_result = {
    "member_id": 1,
    "name": "測試會員",
    "vip": True,
    "member_level": "vip",
    "line_user_id": "U0000000000000000000000000000000",
    "confidence": 0.99,
}

status = notify_vip_recognition(fake_result)
print(f"LINE notify status: {status}")