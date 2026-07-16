"""
AI 人臉偵測與會員比對服務

"""

import os
from datetime import datetime

import cv2
import numpy as np

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
    from database.db import get_member_by_id as db_get_member_by_id
except Exception as e:
    db_get_member_by_id = None
    print(f"警告：無法載入會員查詢函式：{e}")

try:
    from database.db import save_recognition_log as db_save_recognition_log
except Exception as e:
    db_save_recognition_log = None
    print(f"警告：無法載入 recognition_logs 寫入函式：{e}")

try:
    from database.db import (
        insert_vip_notification as db_insert_vip_notification,
        update_vip_notification_status as db_update_vip_notification_status
    )
except Exception as e:
    db_insert_vip_notification = None
    db_update_vip_notification_status = None
    print(f"警告：無法載入 VIP 通知資料庫函式：{e}")

try:
    from database.db import (
        update_recognition_last_seen as db_update_recognition_last_seen,
        close_recognition_visit as db_close_recognition_visit
    )
except Exception as e:
    db_update_recognition_last_seen = None
    db_close_recognition_visit = None
    print(f"警告：無法載入 recognition_logs 更新函式：{e}")

try:
    from database.db import get_all_member_faces
except Exception as e:
    get_all_member_faces = None
    print(f"警告：無法載入會員人臉資料函式：{e}")

try:
    from database.db import insert_face_image
except Exception as e:
    insert_face_image = None
    print(f"警告：無法載入人臉資料寫入函式：{e}")

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
        return "guest"


    if member_level in ("guest", "normal", "vip"):
        return member_level

    if vip:
        return "vip"

    return "normal"


def get_member_level_text(member_level):
    """將 member_level 轉成中文顯示文字。"""

    level_map = {
        "guest": "陌生客",
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
        "subject_type": "member",
        "visitor_id": None,
        "visitor_code": None,
        "member_id": member_id,
        "name": member_data.get("name", "guest"),
        "phone": member_data.get("phone"),
        "vip": vip,
        "member_level": member_level,
        "visit_count": member_data.get("visit_count", 0),
        "line_user_id": member_data.get("line_user_id"),
        "registration_source": member_data.get("registration_source"),
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
            "subject_type": "unknown",
            "member_id": None,
            "visitor_id": None,
            "visitor_code": None,
            "name": "Guest",
            "phone": None,
            "vip": False,
            "member_level": "guest",
            "visit_count": 0,
            "line_user_id": None,
            "total_amount": 0,
            "favorite_product": None,
            "face_image": None,
            "registration_source": None,
            "created_at": None,
            "updated_at": None
    }

    result = {
        **member_data,
        "confidence": confidence,
        "recognition_status": recognition_status,
        "member_level_text": get_member_level_text(
            member_data.get("member_level", "guest")
    )
}
    # 統一辨識主體欄位，避免不同流程缺少 ke
    result.setdefault("subject_type", "unknown")
    result.setdefault("member_id", None)
    result.setdefault("visitor_id", None)
    result.setdefault("visitor_code", None)

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


def register_member_face(member_id, image_path):
    """
    為已建立的會員進行人臉建檔。

    流程：
    1. 驗證照片只有一張人臉
    2. 產生 128 維 encoding
    3. 寫入 face_images
    4. 重新載入會員人臉快取
    """

    if member_id is None:
        return {
            "success": False,
            "message": "member_id 不可為空",
            "member_id": None,
            "face_id": None
        }

    if not image_path:
        return {
            "success": False,
            "message": "image_path 不可為空",
            "member_id": member_id,
            "face_id": None
        }

    if insert_face_image is None:
        return {
            "success": False,
            "message": "人臉資料寫入函式尚未載入",
            "member_id": member_id,
            "face_id": None
        }

    face_result = validate_member_face_image(image_path)

    if not face_result.get("success"):
        return {
            "success": False,
            "message": face_result.get("message", "人臉照片驗證失敗"),
            "member_id": member_id,
            "face_id": None
        }

    encoding = face_result.get("encoding")

    if encoding is None or len(encoding) != 128:
        return {
            "success": False,
            "message": "人臉 encoding 不是有效的 128 維資料",
            "member_id": member_id,
            "face_id": None
        }

    try:
        face_id = insert_face_image(
            member_id=member_id,
            image_path=image_path,
            encoding_data=encoding
        )

        loaded_members = reload_member_faces()

        return {
            "success": True,
            "message": "會員人臉建檔成功",
            "member_id": member_id,
            "face_id": face_id,
            "encoding_length": len(encoding),
            "loaded_member_count": len(loaded_members)
        }

    except Exception as e:
        print(f"會員人臉建檔失敗：{e}")

        return {
            "success": False,
            "message": f"會員人臉建檔失敗：{e}",
            "member_id": member_id,
            "face_id": None
        }


def load_member_faces():
    """
    優先從正式資料庫讀取會員人臉 encoding。
    若資料庫無資料或連線失敗，暫時退回 member_images 假資料。
    """

    if face_recognition is None:
        print("尚未安裝 face_recognition，略過會員人臉資料載入")
        return []

    members = []

    # 先嘗試從正式資料庫載入
    if get_all_member_faces is not None:
        try:
            rows = get_all_member_faces()

            for row in rows:
                encoding_data = row.get("encoding_data")

                if not isinstance(encoding_data, list):
                    continue

                if len(encoding_data) != 128:
                    continue

                member_data = {
                    "member_id": row.get("member_id"),
                    "name": row.get("name", "guest"),
                    "phone": row.get("phone"),
                    "vip": bool(row.get("vip", False)),
                    "member_level": row.get("member_level"),
                    "visit_count": row.get("visit_count", 0),
                    "line_user_id": row.get("line_user_id"),
                    "registration_source": row.get("registration_source"),
                    "total_amount": row.get("total_amount", 0),
                    "favorite_product": row.get("favorite_product"),
                    "face_image": row.get("image_path"),
                    "created_at": row.get("member_created_at"),
                    "updated_at": row.get("member_updated_at"),
                    "encoding": np.array(
                        encoding_data,
                        dtype=float
                    )
                }

                member_data = normalize_member_data(member_data)
                member_data["encoding"] = np.array(
                    encoding_data,
                    dtype=float
                )

                members.append(member_data)

                print(
                    f"已從資料庫載入會員人臉："
                    f"member_id={row.get('member_id')}"
                )

            if members:
                print(
                    f"正式資料庫會員人臉載入完成，共 {len(members)} 筆"
                )
                return members

            print("正式資料庫目前沒有可用的人臉資料，改用 member_images")

        except Exception as e:
            print(f"正式資料庫人臉資料載入失敗，改用 member_images：{e}")

    # 以下保留你原本掃描 member_images 的舊程式
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

        member_data = normalize_member_data(
            get_member_by_image(filename)
        )

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


def check_duplicate_face(encoding, tolerance=0.6):
    """
    檢查新註冊人臉是否已存在於會員人臉快取。

    回傳格式：
    {
        "is_duplicate": bool,
        "member_id": int | None,
        "name": str | None,
        "distance": float | None
    }
    """

    if face_recognition is None:
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    if encoding is None:
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    try:
        encoding = np.array(
            encoding,
            dtype=float
        )
    except (TypeError, ValueError):
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    if encoding.shape != (128,):
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    closest_member = None
    closest_distance = None

    for member in known_members:
        known_encoding = member.get("encoding")

        if known_encoding is None:
            continue

        distance = float(
            face_recognition.face_distance(
                [known_encoding],
                encoding
            )[0]
        )

        if (
            closest_distance is None
            or distance < closest_distance
        ):
            closest_distance = distance
            closest_member = member

    if (
        closest_member is not None
        and closest_distance is not None
        and closest_distance < tolerance
    ):
        return {
            "is_duplicate": True,
            "member_id": closest_member.get("member_id"),
            "name": closest_member.get("name"),
            "distance": round(closest_distance, 4)
        }

    return {
        "is_duplicate": False,
        "member_id": None,
        "name": None,
        "distance": (
            round(closest_distance, 4)
            if closest_distance is not None
            else None
        )
    }


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

def build_recognition_log(result, visit_time=None, leave_time=None, stay_minutes=None, visit_status=None, camera_id=DEFAULT_CAMERA_ID):
    """
    將 AI 辨識結果整理成 recognition_logs 資料表格式。

    recognition_logs 欄位：
    visit_id, member_id, camera_id, confidence, member_level, recognition_status,
    visit_status, visit_time, leave_time, stay_minutes, created_at
    """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        # log_id 由資料庫 AUTO_INCREMENT 產生
        "member_id": result.get("member_id"),
        "name": result.get("name"),
        "vip": result.get("vip", False),
        "line_user_id": result.get("line_user_id"),
        "camera_id": camera_id,
        "confidence": result.get("confidence", 0),
        "member_level": result.get("member_level", "guest"),
        "recognition_status": result.get("recognition_status", "guest"),
        "visit_status": visit_status,
        "recognized_at": now,
        "visit_time": visit_time,
        "leave_time": leave_time,
        "stay_minutes": stay_minutes,
        "created_at": now
    }


def log_recognition_result(result, visit_time=None, leave_time=None, stay_minutes=None, visit_status=None, camera_id=DEFAULT_CAMERA_ID):
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
    

def update_recognition_last_seen(log_id, last_seen_at):
    """
    同一位會員持續出現在鏡頭前時，
    更新原本 recognition_logs 的 last_seen_at，
    不再新增新的辨識紀錄。
    """

    if log_id is None:
        print("更新 last_seen_at 失敗：log_id 不可為空")
        return False

    if db_update_recognition_last_seen is None:
        print("更新 last_seen_at 失敗：資料庫更新函式未成功匯入")
        return False

    try:
        updated_rows = db_update_recognition_last_seen(
            log_id=log_id,
            last_seen_at=last_seen_at
        )

        # 有實際更新資料時才顯示，
        # 避免相同時間造成大量 updated_rows: 0
        if updated_rows > 0:
            print("========== Recognition Log UPDATE ==========")
            print(f"log_id: {log_id}")
            print(f"last_seen_at: {last_seen_at}")
            print("============================================")
            
        return True

    except Exception as e:
        print("========== Recognition Log UPDATE Failed ==========")
        print(f"log_id: {log_id}")
        print(f"error: {e}")
        print("===================================================")

        return False


def close_recognition_visit(
    log_id,
    last_seen_at,
    leave_time,
    stay_seconds,
    stay_minutes
):
    """
    會員超過離店等待時間後，
    更新原本的 recognition_logs 紀錄為 visit_status="left"。
    """

    if log_id is None:
        print("關閉會員到店紀錄失敗：log_id 不可為空")
        return False

    if db_close_recognition_visit is None:
        print("關閉會員到店紀錄失敗：資料庫更新函式未成功匯入")
        return False

    try:
        updated_rows = db_close_recognition_visit(
            log_id=log_id,
            last_seen_at=last_seen_at,
            leave_time=leave_time,
            stay_seconds=stay_seconds,
            stay_minutes=stay_minutes
        )

        print("========== Recognition Visit Closed ==========")
        print(f"log_id: {log_id}")
        print(f"last_seen_at: {last_seen_at}")
        print(f"leave_time: {leave_time}")
        print(f"stay_seconds: {stay_seconds}")
        print(f"stay_minutes: {stay_minutes}")
        print(f"updated_rows: {updated_rows}")
        print("==============================================")

        return updated_rows > 0

    except Exception as e:
        print("========== Close Recognition Visit Failed ==========")
        print(f"log_id: {log_id}")
        print(f"error: {e}")
        print("====================================================")

        return False


def send_line_notify(result, log_id=None):
    """
    發送 LINE VIP 到店通知。

    正確流程：
    1. 確認為 VIP
    2. 確認有 member_id 與 log_id
    3. 先新增 vip_notifications pending 紀錄
    4. 同一個 log_id 已存在時，直接略過推播
    5. 新增成功後才呼叫 LINE
    6. 根據結果更新 sent / failed
    """

    # 只推播 VIP
    if (
        result.get("member_level") != "vip"
        and result.get("vip") is not True
    ):
        return None

    member_id = result.get("member_id")
    line_user_id = result.get("line_user_id")
    name = result.get("name", "VIP 會員")

    if member_id is None:
        print("LINE 推播略過：member_id 不可為空")
        return None

    if log_id is None:
        print("LINE 推播略過：log_id 不可為空")
        return None

    if db_insert_vip_notification is None:
        print("LINE 推播略過：VIP 通知資料庫函式未成功匯入")
        return None

    if notify_vip_recognition is None:
        print("LINE 推播略過：notify_vip_recognition 尚未成功匯入")
        return None

    message = f"VIP會員 {name} 到店了！"

    try:
        # 先建立 pending 紀錄。
        # 若同一個 log_id 已存在，DB 函式會回傳 None。
        notification_id = db_insert_vip_notification(
            member_id=member_id,
            log_id=log_id,
            line_user_id=line_user_id,
            message=message,
            status="pending"
        )

        if notification_id is None:
            print("========== VIP Notification Skipped ==========")
            print(f"log_id: {log_id}")
            print("原因：同一次到店通知已存在，不重複推播")
            print("==============================================")
            return "duplicate"

        # 只有成功取得 notification_id 才真正發送 LINE
        status = notify_vip_recognition(result)

        sent_at = None

        if status == "sent":
            notification_status = "sent"
            sent_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        else:
            notification_status = "failed"

        if db_update_vip_notification_status is not None:
            db_update_vip_notification_status(
                notification_id=notification_id,
                status=notification_status,
                sent_at=sent_at
            )

        print("========== LINE Notification ==========")
        print(f"notification_id: {notification_id}")
        print(f"log_id: {log_id}")
        print(f"VIP 會員到店：{name}")
        print(f"member_id: {member_id}")
        print(f"LINE notify status: {notification_status}")
        print("=======================================")

        return notification_status

    except Exception as e:
        print("========== LINE Notification Failed ==========")
        print(f"log_id: {log_id}")
        print(f"VIP 會員到店：{name}")
        print(f"member_id: {member_id}")
        print(f"LINE notify error: {e}")
        print("==============================================")

        return "failed"
