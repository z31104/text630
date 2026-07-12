"""
AI 人臉偵測與會員比對服務

"""

import os
from datetime import datetime

import cv2

try:
    import face_recognition
except ModuleNotFoundError:
    face_recognition = None
    print("警告：尚未安裝 face_recognition，AI 人臉辨識功能暫時無法使用")

# MVP 階段仍先用圖片檔名找 fake_db 會員資料。
# 正式版會由資料庫同學提供 get_member_by_id(member_id)。
try:
    from database.fake_db import get_member_by_image
except Exception:
    get_member_by_image = None

try:
    from database.member_repository import get_member_by_id as db_get_member_by_id
except Exception:
    db_get_member_by_id = None

try:
    from database.db import save_recognition_log as db_save_recognition_log
except Exception as e:
    db_save_recognition_log = None
    print(f"警告：無法載入 recognition_logs 寫入函式：{e}")

try:
    from linebot_service.notify import notify_vip_recognition
except Exception as e:
    notify_vip_recognition = None
    print(f"警告：無法載入 LINE Bot 推播函式：{e}")


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBER_IMAGE_DIR = os.path.join(BASE_DIR, "member_images")
DEFAULT_CAMERA_ID = "camera_1"


# -----------------------------
# 會員資料欄位統一處理
# -----------------------------

def get_member_level(vip=False, member_id=None, member_level=None):
    """
    統一會員等級名稱。

    guest：陌生客 / 訪客
    normal：一般會員
    vip：VIP 會員
    """

    if member_id is None:
        return "Guest"


    if member_level in ("Guest", "normal", "vip"):
        return member_level

    if vip:
        return "vip"

    return "normal"


def get_member_level_text(member_level):
    """將 member_level 轉成中文顯示文字。"""

    level_map = {
        "Guest": "陌生客",
        "normal": "一般會員",
        "vip": "VIP 會員"
    }

    return level_map.get(member_level, "陌生客")


def normalize_member_data(member_data):
    """
    將 fake_db 或正式 DB 回傳資料整理成 members 資料表欄位名稱。
    """

    if member_data is None:
        return None

    member_id = member_data.get("member_id")
    vip = bool(member_data.get("vip", False))
    member_level = get_member_level(
        vip=vip,
        member_id=member_id,
        member_level=member_data.get("member_level")
    )

    return {
        "member_id": member_id,
        "name": member_data.get("name", "guest"),
        "phone": member_data.get("phone"),
        "vip": vip,
        "member_level": member_level,
        "visit_count": member_data.get("visit_count", 0),
        "line_user_id": member_data.get("line_user_id"),
        "total_amount": member_data.get("total_amount", 0),
        "favorite_product": member_data.get("favorite_product"),
        "face_image": member_data.get("face_image"),
        "created_at": member_data.get("created_at"),
        "updated_at": member_data.get("updated_at")
    }


def build_result(member_data=None, confidence=0, recognition_status="guest"):
    """
    建立統一辨識結果格式。

    欄位盡量對齊 members 資料表：
    member_id, name, phone, vip, member_level, visit_count,
    line_user_id, total_amount, favorite_product, face_image,
    created_at, updated_at
    """

    member_data = normalize_member_data(member_data)

    if member_data is None:
        member_data = {
            "member_id": None,
            "name": "Guest",
            "phone": None,
            "vip": False,
            "member_level": "Guest",
            "visit_count": 0,
            "line_user_id": None,
            "total_amount": 0,
            "favorite_product": None,
            "face_image": None,
            "created_at": None,
            "updated_at": None
        }

    result = {
        **member_data,
        "confidence": confidence,
        "recognition_status": recognition_status,
        "member_level_text": get_member_level_text(member_data["member_level"])
    }


    return result


def get_member_by_id(member_id):
    """
    查詢會員資料。
    """
    if member_id is None:
        return None

    if db_get_member_by_id is not None:
        try:
            return normalize_member_data(db_get_member_by_id(member_id))
        except Exception as e:
            print(f"正式資料庫查詢失敗，改用 known_members：{e}")

    for member in known_members:
        if member.get("member_id") == member_id:
            return normalize_member_data(member)

    return None

# -----------------------------
# 人臉資料載入與辨識
# -----------------------------

# 第三週的新函式 validate_member_face_image
def validate_member_face_image(image_path):
    """
    驗證新會員上傳的照片。

    條件：
    1. 照片必須存在
    2. 照片必須剛好只有一張人臉
    3. 成功後回傳 128 維 encoding
    """

    if face_recognition is None:
        return {
            "success": False,
            "message": "尚未安裝 face_recognition",
            "encoding": None
        }

    if not image_path or not os.path.exists(image_path):
        return {
            "success": False,
            "message": "找不到會員照片",
            "encoding": None
        }

    try:
        image = face_recognition.load_image_file(image_path)
        face_locations = face_recognition.face_locations(image)
    except Exception as e:
        return {
            "success": False,
            "message": f"照片讀取失敗：{e}",
            "encoding": None
        }

    if len(face_locations) == 0:
        return {
            "success": False,
            "message": "照片中沒有偵測到人臉",
            "encoding": None
        }

    if len(face_locations) > 1:
        return {
            "success": False,
            "message": "照片中偵測到多張人臉，請只上傳單人照片",
            "encoding": None
        }

    encodings = face_recognition.face_encodings(
        image,
        face_locations
    )

    if len(encodings) == 0:
        return {
            "success": False,
            "message": "無法建立人臉特徵",
            "encoding": None
        }

    return {
        "success": True,
        "message": "人臉照片驗證成功",
        "encoding": encodings[0]
    }


def load_member_faces():
    """讀取 member_images 資料夾中的會員圖片，並轉成人臉特徵資料。"""

    if face_recognition is None:
        print("尚未安裝 face_recognition，略過會員人臉資料載入")
        return []

    members = []

    if not os.path.exists(MEMBER_IMAGE_DIR):
        print("找不到會員圖片資料夾:", MEMBER_IMAGE_DIR)
        return members

    for filename in os.listdir(MEMBER_IMAGE_DIR):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        image_path = os.path.join(MEMBER_IMAGE_DIR, filename)

        try:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
        except Exception as e:
            print(f"會員圖片讀取或編碼失敗：{filename}，原因：{e}")
            continue

        if len(encodings) == 0:
            print(f"會員圖片找不到人臉：{filename}")
            continue

        if get_member_by_image is None:
            print("找不到 fake_db.get_member_by_image，無法載入會員假資料")
            continue

        # MVP 階段先用圖片檔名找會員資料；正式版會改成會員人臉資料表。
        member_data = normalize_member_data(get_member_by_image(filename))

        if member_data is None:
            print(f"假資料庫找不到對應會員：{filename}")
            continue

        member_data["encoding"] = encodings[0]
        members.append(member_data)

        print(f"已載入會員人臉：{filename}")

    print(f"會員人臉資料載入完成，共 {len(members)} 筆")
    return members


known_members = load_member_faces()

def reload_member_faces():
    """
    重新載入會員人臉資料。

    新會員註冊完成後可以呼叫，
    讓攝影機不用重新啟動 app.py 就能辨識新會員。
    """

    global known_members

    known_members = load_member_faces()

    print(
        f"會員人臉資料已重新載入，共 {len(known_members)} 筆"
    )

    return known_members


face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def detect_face(frame):
    """偵測畫面中的人臉，並過濾明顯不合理的誤判框。"""

    if frame is None:
        return []

    if face_cascade.empty():
        print("Haar Cascade 載入失敗，無法偵測人臉")
        return []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 改善光線差異
    gray = cv2.equalizeHist(gray)

    detected_faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.15,
        minNeighbors=7,
        minSize=(90, 90),
        maxSize=(450, 450)
    )

    frame_height, frame_width = frame.shape[:2]
    valid_faces = []

    for x, y, w, h in detected_faces:
        aspect_ratio = w / float(h)

        # 一般正面人臉框比例通常接近正方形
        if not 0.75 <= aspect_ratio <= 1.30:
            continue

        center_x = x + w / 2
        center_y = y + h / 2

        # 排除過度靠近畫面四周的誤判
        if center_x < frame_width * 0.03:
            continue

        if center_x > frame_width * 0.97:
            continue

        if center_y < frame_height * 0.03:
            continue

        if center_y > frame_height * 0.97:
            continue

        valid_faces.append((x, y, w, h))

    return valid_faces


def recognize_face(frame, faces):
    """
    辨識會員。

    回傳欄位名稱已統一為：
    member_id, name, phone, vip, member_level, visit_count,
    line_user_id, total_amount, favorite_product, face_image,
    confidence, recognition_status
    """

    if face_recognition is None:
        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    # 畫面完全沒有偵測到人臉
    if len(faces) == 0:
        return build_result(
            confidence=0,
            recognition_status="no_face"
        )

    # 有偵測到臉，但沒有任何會員人臉資料可供比對
    # 這種情況視為 guest
    if len(known_members) == 0:
        return build_result(
            confidence=0,
            recognition_status="guest"
        )

    rgb_frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    # MVP 階段先只處理第一張臉
    x, y, w, h = faces[0]
    face_location = (
        y,
        x + w,
        y + h,
        x
    )

    try:
        encodings = face_recognition.face_encodings(
            rgb_frame,
            [face_location]
        )

    except Exception as e:
        print(f"即時人臉編碼失敗：{e}")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    if len(encodings) == 0:
        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    current_encoding = encodings[0]

    for member in known_members:
        if "encoding" not in member:
            continue

        distance = face_recognition.face_distance(
            [member["encoding"]],
            current_encoding
        )[0]

        confidence = float(
            round(1 - distance, 2)
        )

        if distance < 0.6:
            member_data = (
                get_member_by_id(member["member_id"])
                or member
            )

            return build_result(
                member_data=member_data,
                confidence=confidence,
                recognition_status="recognized"
            )

    # 有偵測到人臉，但沒有比對到任何會員
    return build_result(
        confidence=0,
        recognition_status="guest"
    )


# -----------------------------
# 畫面顯示
# -----------------------------

def draw_face_boxes(frame, faces, result=None):
    """
    在畫面上畫出人臉框框。
    OpenCV cv2.putText 不支援中文，所以畫面上用英文顯示，
    但 log / 資料庫仍保留中文姓名與中文類型。
    """

    if result is None:
        result = recognize_face(frame, faces)

    member_level = result.get("member_level", "guest")

    if member_level == "vip":
        display_name = f"Member ID: {result['member_id']}"
        member_type = "VIP Member"
        box_name = f"VIP {result['member_id']}"
    elif member_level == "normal":
        display_name = f"Member ID: {result['member_id']}"
        member_type = "Normal Member"
        box_name = f"Member {result['member_id']}"
    else:
        display_name = "guest"
        member_type = "guest"
        box_name = "guest"

    cv2.putText(frame, f"Name: {display_name}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Type: {member_type}", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Confidence: {result.get('confidence', 0)}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, box_name, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    return frame


# -----------------------------
# recognition_logs 欄位統一處理
# -----------------------------

def build_recognition_log(result, visit_time=None, leave_time=None, stay_minutes=None, visit_status="recognition", camera_id=DEFAULT_CAMERA_ID):
    """
    將 AI 辨識結果整理成 recognition_logs 資料表格式。

    recognition_logs 欄位：
    visit_id, member_id, camera_id, confidence, member_level, recognition_status,
    visit_status, visit_time, leave_time, stay_minutes, created_at
    """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        # visit_id 由資料庫 AUTO_INCREMENT 產生，Python 不需要給
        "member_id": result.get("member_id"),
        "camera_id": camera_id,
        "confidence": result.get("confidence", 0),
        "member_level": result.get("member_level", "guest"),
        "recognition_status": result.get("recognition_status", "guest"),
        "visit_status": visit_status,
        "visit_time": visit_time,
        "leave_time": leave_time,
        "stay_minutes": stay_minutes,
        "created_at": now
    }


def log_recognition_result(result, visit_time=None, leave_time=None, stay_minutes=None, visit_status="recognition", camera_id=DEFAULT_CAMERA_ID):
    """
    將 AI 辨識結果印在終端機，並整理成 recognition_logs INSERT 格式。
    """

    recognition_log = build_recognition_log(
        result,
        visit_time=visit_time,
        leave_time=leave_time,
        stay_minutes=stay_minutes,
        visit_status=visit_status,
        camera_id=camera_id
    )

    print("========== Recognition Log ==========")
    print(f"member_id: {recognition_log['member_id']}")
    print(f"camera_id: {recognition_log['camera_id']}")
    print(f"confidence: {recognition_log['confidence']}")
    print(f"member_level: {recognition_log['member_level']}")
    print(f"recognition_status: {recognition_log['recognition_status']}")
    print(f"visit_status: {recognition_log['visit_status']}")
    print(f"visit_time: {recognition_log['visit_time']}")
    print(f"leave_time: {recognition_log['leave_time']}")
    print(f"stay_minutes: {recognition_log['stay_minutes']}")
    print(f"created_at: {recognition_log['created_at']}")
    print("=====================================")

    return save_recognition_log(recognition_log)


def save_recognition_log(recognition_log):
    """
    將 recognition_log 寫入 MySQL。

    資料庫錯誤由 database.db 負責 rollback 與 close；
    此處捕捉錯誤，避免攝影機串流因單次寫入失敗而中斷。
    """
    if db_save_recognition_log is None:
        print("recognition_logs 寫入失敗：資料庫寫入函式未成功匯入")
        return None

    try:
        log_id = db_save_recognition_log(recognition_log)

        print("========== recognition_logs INSERT success ==========")
        print(f"log_id: {log_id}")
        print("=====================================================")

        return log_id

    except Exception as e:
        print("========== recognition_logs INSERT failed ==========")
        print(f"error: {e}")
        print("====================================================")

        return None

def send_line_notify(result):
    """
    發送 LINE VIP 到店通知。

    觸發條件：
    - 必須是 VIP
    - 必須有 member_id
    - 必須成功載入 LINE Bot 組提供的 notify_vip_recognition()

    注意：
    - LINE 推播失敗時，不讓攝影機串流中斷
    """

    # 只推播 VIP，不是 VIP 就不處理
    if result.get("member_level") != "vip" and result.get("vip") is not True:
        return None

    # 沒有會員 ID，代表不是正式會員資料，不推播
    if result.get("member_id") is None:
        return None

    # LINE Bot 組功能尚未接上時，不讓攝影機程式當掉
    if notify_vip_recognition is None:
        print("LINE 推播略過：notify_vip_recognition 尚未成功匯入")
        return None

    try:
        # 呼叫 LINE Bot 組的推播函式，取得回傳結果
        status = notify_vip_recognition(result)

        print("========== LINE Notification ==========")
        print(f"VIP 會員到店：{result.get('name')}")
        print(f"member_id: {result.get('member_id')}")
        print(f"line_user_id: {result.get('line_user_id')}")
        print(f"LINE notify status: {status}")
        print("=======================================")

        return status

    except Exception as e:
        print("========== LINE Notification Failed ==========")
        print(f"VIP 會員到店：{result.get('name')}")
        print(f"member_id: {result.get('member_id')}")
        print(f"line_user_id: {result.get('line_user_id')}")
        print(f"LINE notify error: {e}")
        print("==============================================")

        # 推播失敗時回傳 failed，但不要讓 camera 串流當掉
        return "failed"
