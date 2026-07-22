"""
AI 人臉偵測與會員比對服務

"""

import os
import uuid
from datetime import datetime

import cv2
import numpy as np
from PIL import (
    Image,
    ImageOps,
    ImageDraw,
    ImageFont,
)

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
    from database.db import (
        get_all_member_faces,
        get_all_visitor_faces
    )
except Exception as e:
    get_all_member_faces = None
    get_all_visitor_faces = None
    print(f"警告：無法載入會員或散客人臉資料函式：{e}")

try:
    from database.db import insert_face_image
except Exception as e:
    insert_face_image = None
    print(f"警告：無法載入人臉資料寫入函式：{e}")

try:
    from database.db import (
        register_visitor_with_face as db_register_visitor_with_face
    )
except Exception as e:
    db_register_visitor_with_face = None
    print(f"警告：無法載入散客人臉建檔函式：{e}")

try:
    from linebot_service.notify import notify_vip_recognition
except Exception as e:
    notify_vip_recognition = None
    print(f"警告：無法載入 LINE Bot 推播函式：{e}")


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows 內建繁體中文字型
# 用於 Pillow 在 OpenCV 畫面上顯示中文。
CHINESE_FONT_PATH = r"C:\Windows\Fonts\msjhbd.ttc"


def draw_chinese_text(
    frame,
    text,
    position,
    font_size=28,
    color=(0, 255, 0)
):
    """
    使用 Pillow 在 OpenCV 畫面上顯示中文。

    frame：OpenCV BGR 畫面
    text：要顯示的文字
    position：(x, y)
    font_size：字體大小
    color：OpenCV BGR 顏色
    """

    if frame is None:
        return frame

    if not os.path.exists(CHINESE_FONT_PATH):
        print(
            "找不到中文字型："
            f"{CHINESE_FONT_PATH}"
        )
        return frame

    try:
        # OpenCV BGR → RGB
        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        pil_image = Image.fromarray(rgb_frame)
        draw = ImageDraw.Draw(pil_image)

        font = ImageFont.truetype(
            CHINESE_FONT_PATH,
            font_size
        )

        # OpenCV BGR → Pillow RGB
        b, g, r = color
        pillow_color = (r, g, b)

        draw.multiline_text(
            position,
            str(text),
            font=font,
            fill=pillow_color,
            spacing=6
        )

        # Pillow RGB → OpenCV BGR
        return cv2.cvtColor(
            np.array(pil_image),
            cv2.COLOR_RGB2BGR
        )

    except Exception as e:
        print(f"中文文字繪製失敗：{e}")
        return frame


MEMBER_IMAGE_DIR = os.path.join(
    BASE_DIR,
    "member_images"
)

VISITOR_IMAGE_DIR = os.path.join(
    BASE_DIR,
    "visitor_images"
)

# visitor_images 不存在時自動建立
os.makedirs(
    VISITOR_IMAGE_DIR,
    exist_ok=True
)

DEFAULT_CAMERA_ID = os.getenv("CAMERA_ID", "camera_1")
DEFAULT_CAMERA_LOCATION = os.getenv("CAMERA_LOCATION", "入口")

# 人臉距離越小代表越相似
# 正式會員維持原本 0.6
MEMBER_MATCH_TOLERANCE = 0.6

# 散客使用稍嚴格門檻，降低兩位陌生人被當成同一 visitor 的風險
VISITOR_MATCH_TOLERANCE = 0.55


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
        # 第四週統一欄位：不再使用 visit_count
        "total_visit_count": member_data.get("total_visit_count", 0),
        "last_visit_time": member_data.get("last_visit_time"),
        "total_visit_time": member_data.get("total_visit_time", 0),
        "updated_by": member_data.get("updated_by"),
        "line_user_id": member_data.get("line_user_id"),
        "registration_source": member_data.get("registration_source"),
        "total_amount": member_data.get("total_amount", 0),
        "favorite_product": member_data.get("favorite_product"),
        "face_image": member_data.get("face_image"),
        "created_at": member_data.get("created_at"),
        "updated_at": member_data.get("updated_at")
    }


def normalize_visitor_data(visitor_data):
    """
    將 visitors 與 visitor_faces 查詢結果，
    整理成 AI 辨識流程統一使用的散客格式。
    """

    if visitor_data is None:
        return None

    visitor_id = visitor_data.get("visitor_id")
    visitor_code = visitor_data.get("visitor_code")

    if visitor_id is None:
        return None

    return {
        "subject_type": "visitor",
        "member_id": None,
        "visitor_id": visitor_id,
        "visitor_code": visitor_code,
        "name": (
            visitor_data.get("display_name")
            or visitor_code
            or f"Visitor {visitor_id}"
        ),
        "phone": None,
        "vip": False,
        "member_level": "guest",
        "total_visit_count": 0,
        "last_visit_time": None,
        "total_visit_time": 0,
        "updated_by": None,
        "visitor_visit_count": visitor_data.get("visitor_visit_count", 0),
        "converted_member_id": visitor_data.get("converted_member_id"),
        "best_face_image": (
            visitor_data.get("best_face_image")
            or visitor_data.get("image_path")
        ),
        "line_user_id": None,
        "registration_source": None,
        "total_amount": 0,
        "favorite_product": None,
        "face_image": visitor_data.get("image_path"),
        "first_seen_at": visitor_data.get("first_seen_at"),
        "last_seen_at": visitor_data.get("last_seen_at"),
        "created_at": (
            visitor_data.get("visitor_created_at")
            or visitor_data.get("created_at")
        ),
        "updated_at": (
            visitor_data.get("visitor_updated_at")
            or visitor_data.get("updated_at")
        )
    }


def build_result(member_data=None,visitor_data=None,confidence=0,recognition_status="guest"):
    """
    建立統一辨識結果格式。

    支援三種辨識主體：
    1. member：正式會員
    2. visitor：已建檔固定散客
    3. unknown：尚未建立固定身分的陌生人
    """

    normalized_data = None

    # 正式會員
    if member_data is not None:
        normalized_data = normalize_member_data(member_data)

    # 已建檔散客
    elif visitor_data is not None:
        normalized_data = normalize_visitor_data(visitor_data)

    # 尚未辨識出固定身分
    if normalized_data is None:
        normalized_data = {
            "subject_type": "unknown",
            "member_id": None,
            "visitor_id": None,
            "visitor_code": None,
            "name": "Guest",
            "phone": None,
            "vip": False,
            "member_level": "guest",
            "total_visit_count": 0,
            "last_visit_time": None,
            "total_visit_time": 0,
            "updated_by": None,
            "visitor_visit_count": 0,
            "converted_member_id": None,
            "best_face_image": None,
            "line_user_id": None,
            "registration_source": None,
            "total_amount": 0,
            "favorite_product": None,
            "face_image": None,
            "created_at": None,
            "updated_at": None
        }

    result = {
        **normalized_data,
        "log_id": None,
        "camera_id": DEFAULT_CAMERA_ID,
        "camera_location": DEFAULT_CAMERA_LOCATION,
        "confidence": confidence,
        "recognition_status": recognition_status,
        "visit_status": None,
        "recognized_at": None,
        "visit_time": None,
        "last_seen_at": normalized_data.get("last_seen_at"),
        "leave_time": None,
        "stay_seconds": 0,
        "notification_sent": False,
        "coupon_sent": False,
        "lottery_status": "not_joined" if normalized_data.get("member_id") is not None else None,
        "member_level_text": get_member_level_text(
            normalized_data.get("member_level", "guest")
        )
    }

    # 避免不同流程漏掉辨識主體欄位
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
        print("=" * 50)
        print("開始驗證會員照片")
        print("image_path:", image_path)
        print("file_size:", os.path.getsize(image_path), "bytes")
        
        with Image.open(image_path) as pil_image:
            # 依手機照片的 EXIF Orientation 自動轉正
            pil_image = ImageOps.exif_transpose(pil_image)
            
            # 統一轉成 RGB，避免灰階、RGBA 等格式造成問題
            pil_image = pil_image.convert("RGB")
            
            # 轉成 face_recognition 可使用的 NumPy 陣列
            image = np.array(pil_image)

        cv2.imwrite(
            "debug_upload.jpg",
            cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        )
        
        print("已輸出 debug_upload.jpg")
        
        print("原始 image shape:", image.shape)
        
        height, width = image.shape[:2]
        
        # 大型手機照片先等比例縮小，避免偵測太慢
        max_width = 1200
        
        if width > max_width:
            scale = max_width / width
            resized_width = int(width * scale)
            resized_height = int(height * scale)
            
            image_for_detection = cv2.resize(
                image,
                (resized_width, resized_height)
            )
            
        else:
            scale = 1.0
            image_for_detection = image
        
        print("偵測用 image shape:", image_for_detection.shape)
        print("縮放比例:", scale)
        
        face_locations_small = face_recognition.face_locations(
            image_for_detection,
            number_of_times_to_upsample=2,
            model="hog"
        )
        
        # 把縮小圖片上的座標換算回原圖
        face_locations = []
        
        for top, right, bottom, left in face_locations_small:
            original_top = max(0, int(round(top / scale)))
            original_right = min(width, int(round(right / scale)))
            original_bottom = min(height, int(round(bottom / scale)))
            original_left = max(0, int(round(left / scale)))
            
            face_locations.append((
                original_top,
                original_right,
                original_bottom,
                original_left
            ))
        
        print("face_locations:", face_locations)
        print("偵測到人臉數量:", len(face_locations))
        print("=" * 50)
        
    except Exception as e:
        print("照片驗證發生錯誤:", e)
        
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
                    "total_visit_count": row.get("total_visit_count", 0),
                    "last_visit_time": row.get("last_visit_time"),
                    "total_visit_time": row.get("total_visit_time", 0),
                    "updated_by": row.get("updated_by"),
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



def load_visitor_faces():
    """
    從正式資料庫載入既有散客的人臉 encoding。

    Flask 啟動時會執行此函式，
    因此即使程式重新啟動，
    仍能從 visitor_faces 重新取得散客人臉資料。
    """

    if face_recognition is None:
        print("尚未安裝 face_recognition，略過散客人臉資料載入")
        return []

    if get_all_visitor_faces is None:
        print("散客人臉資料函式尚未載入")
        return []

    visitors = []

    try:
        rows = get_all_visitor_faces()

        for row in rows:
            encoding_data = row.get("encoding_data")

            if not isinstance(encoding_data, list):
                print(
                    f"略過無效散客 encoding："
                    f"visitor_id={row.get('visitor_id')}"
                )
                continue

            if len(encoding_data) != 128:
                print(
                    f"略過非 128 維散客 encoding："
                    f"visitor_id={row.get('visitor_id')}，"
                    f"目前維度={len(encoding_data)}"
                )
                continue

            visitor_data = normalize_visitor_data(row)

            if visitor_data is None:
                continue

            visitor_data["encoding"] = np.array(
                encoding_data,
                dtype=float
            )

            visitors.append(visitor_data)

            print(
                f"已從資料庫載入散客人臉："
                f"visitor_id={visitor_data.get('visitor_id')}，"
                f"visitor_code={visitor_data.get('visitor_code')}"
            )

        print(
            f"正式資料庫散客人臉載入完成，"
            f"共 {len(visitors)} 筆"
        )

        return visitors

    except Exception as e:
        print(f"正式資料庫散客人臉資料載入失敗：{e}")
        return []



known_members = load_member_faces()
known_visitors = load_visitor_faces()


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


def reload_visitor_faces():
    """
    重新載入散客人臉資料。

    新散客建立並寫入 visitor_faces 後呼叫，
    不需要重新啟動 Flask，
    就能立刻把新散客加入辨識名單。
    """

    global known_visitors

    known_visitors = load_visitor_faces()

    print(
        f"散客人臉資料已重新載入，"
        f"共 {len(known_visitors)} 筆"
    )

    return known_visitors


def generate_visitor_code():
    """
    產生固定散客代碼。

    格式：
    V + 年月日時分秒微秒 + 6 碼 UUID

    例如：
    V20260717143025123456A1B2C3
    """

    timestamp_text = datetime.now().strftime(
        "%Y%m%d%H%M%S%f"
    )

    random_text = uuid.uuid4().hex[:6].upper()

    return f"V{timestamp_text}{random_text}"


def register_new_visitor(frame, faces):
    """
    將目前鏡頭中的未知人臉建立為固定散客。

    流程：
    1. 取畫面中最大的人臉
    2. 產生 128 維 encoding
    3. 裁切並保存人臉圖片
    4. 產生 visitor_code
    5. 同一個 transaction 寫入 visitors 與 visitor_faces
    6. 重新載入 known_visitors
    7. 回傳統一 visitor 辨識結果
    """

    if face_recognition is None:
        print("建立新散客失敗：face_recognition 尚未載入")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    if db_register_visitor_with_face is None:
        print("建立新散客失敗：資料庫建檔函式尚未載入")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    if frame is None:
        print("建立新散客失敗：frame 不可為空")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    if not faces:
        print("建立新散客失敗：目前沒有偵測到人臉")

        return build_result(
            confidence=0,
            recognition_status="no_face"
        )

    # 選取畫面中面積最大的人臉
    x, y, w, h = max(
        faces,
        key=lambda face: face[2] * face[3]
    )

    frame_height, frame_width = frame.shape[:2]

    # 在人臉框四周保留一點範圍，
    # 避免裁切得太貼近五官
    margin_x = int(w * 0.20)
    margin_y = int(h * 0.20)

    crop_left = max(
        x - margin_x,
        0
    )
    crop_top = max(
        y - margin_y,
        0
    )
    crop_right = min(
        x + w + margin_x,
        frame_width
    )
    crop_bottom = min(
        y + h + margin_y,
        frame_height
    )

    face_crop = frame[
        crop_top:crop_bottom,
        crop_left:crop_right
    ]

    if face_crop.size == 0:
        print("建立新散客失敗：人臉裁切結果為空")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    rgb_frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

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
        print(f"建立散客人臉 encoding 失敗：{e}")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    if len(encodings) == 0:
        print("建立新散客失敗：無法產生人臉 encoding")

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    current_encoding = encodings[0]

    if len(current_encoding) != 128:
        print(
            "建立新散客失敗："
            f"encoding 維度為 {len(current_encoding)}"
        )

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    visitor_code = generate_visitor_code()

    image_filename = f"{visitor_code}.jpg"

    image_path = os.path.join(
        VISITOR_IMAGE_DIR,
        image_filename
    )

    image_saved = cv2.imwrite(
        image_path,
        face_crop
    )

    if not image_saved:
        print(
            "建立新散客失敗："
            f"照片儲存失敗，image_path={image_path}"
        )

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    try:
        registration_result = db_register_visitor_with_face(
            visitor_code=visitor_code,
            image_path=image_path,
            encoding_data=current_encoding,
            display_name=visitor_code,
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now()
        )

        visitor_id = registration_result.get(
            "visitor_id"
        )

        visitor_face_id = registration_result.get(
            "visitor_face_id"
        )

        if visitor_id is None:
            raise RuntimeError(
                "資料庫未回傳 visitor_id"
            )

        # 不需重啟 Flask，立即把新散客加入快取
        loaded_visitors = reload_visitor_faces()

        visitor_data = None

        for visitor in loaded_visitors:
            if visitor.get("visitor_id") == visitor_id:
                visitor_data = visitor
                break

        # 正常情況應該可從 reload 後找到；
        # 若暫時找不到，仍先建立基本回傳資料。
        if visitor_data is None:
            visitor_data = {
                "subject_type": "visitor",
                "member_id": None,
                "visitor_id": visitor_id,
                "visitor_code": visitor_code,
                "display_name": visitor_code,
                "visitor_visit_count": 0,
                "converted_member_id": None,
                "best_face_image": image_path,
                "image_path": image_path,
                "first_seen_at": datetime.now(),
                "last_seen_at": datetime.now()
            }

        print("========== New Visitor Created ==========")
        print(f"visitor_id: {visitor_id}")
        print(f"visitor_code: {visitor_code}")
        print(f"visitor_face_id: {visitor_face_id}")
        print(f"image_path: {image_path}")
        print(
            f"known_visitors count: "
            f"{len(loaded_visitors)}"
        )
        print("=========================================")

        return build_result(
            visitor_data=visitor_data,
            confidence=1.0,
            recognition_status="recognized"
        )

    except Exception as e:
        print("========== New Visitor Creation Failed ==========")
        print(f"visitor_code: {visitor_code}")
        print(f"error: {e}")
        print("=================================================")

        # DB 建檔失敗時刪除已保存的孤立照片
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                print(
                    "已刪除未完成建檔的散客照片："
                    f"{image_path}"
                )
        except Exception as delete_error:
            print(
                "刪除散客照片失敗："
                f"{delete_error}"
            )

        return build_result(
            confidence=0,
            recognition_status="failed"
        )


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


def detect_face(frame):
    """
    使用 face_recognition 的 HOG 模型偵測人臉。

    為提升攝影機流暢度，先將畫面縮小至 50% 偵測，
    再將座標換算回原始畫面。

    face_recognition.face_locations() 原始格式：
    (top, right, bottom, left)

    為相容目前 camera.py 與畫框流程，
    最後仍回傳：
    (x, y, w, h)
    """

    if frame is None:
        return []

    if face_recognition is None:
        print("face_recognition 尚未載入，無法偵測人臉")
        return []

    detection_scale = 0.5

    small_frame = cv2.resize(
        frame,
        None,
        fx=detection_scale,
        fy=detection_scale,
        interpolation=cv2.INTER_LINEAR
    )

    # OpenCV 為 BGR，face_recognition 需要 RGB。
    rgb_small_frame = cv2.cvtColor(
        small_frame,
        cv2.COLOR_BGR2RGB
    )

    try:
        detected_locations = face_recognition.face_locations(
            rgb_small_frame,
            number_of_times_to_upsample=0,
            model="hog"
        )
    except Exception as e:
        print(f"HOG 人臉偵測失敗：{e}")
        return []

    frame_height, frame_width = frame.shape[:2]
    valid_faces = []

    for (
        small_top,
        small_right,
        small_bottom,
        small_left
    ) in detected_locations:

        x = int(small_left / detection_scale)
        y = int(small_top / detection_scale)

        right = int(small_right / detection_scale)
        bottom = int(small_bottom / detection_scale)

        w = right - x
        h = bottom - y

        # 防止換算後超出原始畫面範圍。
        x = max(0, x)
        y = max(0, y)

        w = min(w, frame_width - x)
        h = min(h, frame_height - y)

        if w <= 0 or h <= 0:
            continue

        aspect_ratio = w / float(h)

        # 排除明顯不合理的人臉框。
        if not 0.65 <= aspect_ratio <= 1.45:
            continue

        center_x = x + w / 2
        center_y = y + h / 2

        # 排除過度靠近畫面四周的偵測結果。
        if center_x < frame_width * 0.03:
            continue

        if center_x > frame_width * 0.97:
            continue

        if center_y < frame_height * 0.03:
            continue

        if center_y > frame_height * 0.97:
            continue

        valid_faces.append(
            (x, y, w, h)
        )

    # 目前階段只處理單人辨識：
    # 多個人臉時，只保留面積最大的一張臉。
    if valid_faces:
        largest_face = max(
            valid_faces,
            key=lambda face: face[2] * face[3]
        )

        return [largest_face]

    return []

def recognize_face(frame, faces):
    """
    人臉辨識流程：

    1. 取得目前畫面人臉 encoding
    2. 優先比對正式會員 known_members
    3. 會員未命中後，再比對既有散客 known_visitors
    4. 兩者都未命中時回傳 unknown guest
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

    rgb_frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    # 優先辨識畫面中面積最大的人臉
    x, y, w, h = max(
        faces,
        key=lambda face: face[2] * face[3]
    )

    face_location = (
        y,          # top
        x + w,      # right
        y + h,      # bottom
        x           # left
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

    # ==================================================
    # 第一層：優先比對正式會員
    # ==================================================

    member_encodings = []
    valid_members = []

    for member in known_members:
        known_encoding = member.get("encoding")

        if known_encoding is None:
            continue

        member_encodings.append(known_encoding)
        valid_members.append(member)

    if member_encodings:
        member_distances = face_recognition.face_distance(
            member_encodings,
            current_encoding
        )

        member_best_index = int(
            np.argmin(member_distances)
        )

        member_best_distance = float(
            member_distances[member_best_index]
        )

        member_best_data = valid_members[
            member_best_index
        ]

        member_confidence = float(
            round(1 - member_best_distance, 2)
        )

        print(
            "會員最佳比對："
            f"member_id={member_best_data.get('member_id')}，"
            f"distance={round(member_best_distance, 4)}"
        )

        if member_best_distance < MEMBER_MATCH_TOLERANCE:
            return build_result(
                member_data=member_best_data,
                confidence=member_confidence,
                recognition_status="recognized"
            )

    # ==================================================
    # 第二層：會員未命中，再比對既有散客
    # ==================================================

    visitor_encodings = []
    valid_visitors = []

    for visitor in known_visitors:
        known_encoding = visitor.get("encoding")

        if known_encoding is None:
            continue

        visitor_encodings.append(known_encoding)
        valid_visitors.append(visitor)

    if visitor_encodings:
        visitor_distances = face_recognition.face_distance(
            visitor_encodings,
            current_encoding
        )

        visitor_best_index = int(
            np.argmin(visitor_distances)
        )

        visitor_best_distance = float(
            visitor_distances[visitor_best_index]
        )

        visitor_best_data = valid_visitors[
            visitor_best_index
        ]

        visitor_confidence = float(
            round(1 - visitor_best_distance, 2)
        )

        print(
            "散客最佳比對："
            f"visitor_id={visitor_best_data.get('visitor_id')}，"
            f"visitor_code={visitor_best_data.get('visitor_code')}，"
            f"distance={round(visitor_best_distance, 4)}"
        )

        if visitor_best_distance < VISITOR_MATCH_TOLERANCE:
            return build_result(
                visitor_data=visitor_best_data,
                confidence=visitor_confidence,
                recognition_status="recognized"
            )

    # ==================================================
    # 第三層：會員與既有散客都沒有命中
    # ==================================================

    return build_result(
        confidence=0,
        recognition_status="guest"
    )

# -----------------------------
# 畫面顯示
# -----------------------------

def draw_face_boxes(frame, faces, result=None, current_fps=None):
    """
    在畫面上顯示統一的辨識標籤。

    顯示規則：
    - VIP 會員：VIP
    - 一般會員：Member
    - 已建檔散客：Visitor
    - 陌生人確認中：Detecting
    - 尚未建檔陌生人：Guest
    - 辨識失敗：Failed

    OpenCV 的 cv2.putText 不支援中文，
    因此攝影機畫面使用英文標籤。
    """

    if result is None:
        result = recognize_face(
            frame,
            faces
        )

    subject_type = result.get(
        "subject_type",
        "unknown"
    )

    member_level = result.get(
        "member_level",
        "guest"
    )

    recognition_status = result.get(
        "recognition_status",
        "no_face"
    )

    name = result.get("name") or ""
    member_id = result.get("member_id")
    visitor_id = result.get("visitor_id")
    confidence = result.get("confidence", 0)

    # =============================
    # 統一畫面顯示標籤
    # =============================

    if recognition_status == "detecting":
        display_name = "Detecting"
        display_type = "Detecting"
        box_label = "Detecting"

    elif recognition_status == "failed":
        display_name = "Recognition Failed"
        display_type = "Failed"
        box_label = "Failed"

    elif (
        subject_type == "visitor"
        and visitor_id is not None
    ):
        # 不再顯示完整 visitor_code，
        # 避免文字過長與其他欄位重疊。
        display_name = f"Visitor ID: {visitor_id}"
        display_type = "Visitor"
        box_label = "Visitor"

    elif (
        subject_type == "member"
        and member_level == "vip"
        and member_id is not None
    ):
        display_name = (
            name
            if name
            else f"Member ID: {member_id}"
        )
        display_type = "VIP"
        box_label = (
            name
            if name
            else "VIP"
        )

    elif (
        subject_type == "member"
        and member_id is not None
    ):
        display_name = (
            name
            if name
            else f"Member ID: {member_id}"
        )
        display_type = "Member"
        box_label = (
            name
            if name
            else "Member"
        )

    else:
        display_name = "Guest"
        display_type = "Guest"
        box_label = "Guest"

    # =============================
    # 左上角辨識資訊
    # =============================

    info_text = (
        f"Name: {display_name}\n"
        f"Type: {display_type}\n"
        f"Confidence: {confidence}"
    )
    if current_fps is not None:
        info_text += f"\nFPS: {current_fps:.1f}"

    frame = draw_chinese_text(
        frame,
        info_text,
        (20, 15),
        font_size=27,
        color=(0, 255, 0)
    )

    # =============================
    # 人臉框與框上標籤
    # =============================

    for x, y, w, h in faces:
        cv2.rectangle(
            frame,
            (x, y),
            (x + w, y + h),
            (0, 255, 0),
            2
        )

        label_y = max(
            y - 32,
            0
        )

        frame = draw_chinese_text(
            frame,
            box_label,
            (x, label_y),
            font_size=24,
            color=(0, 255, 0)
        )

    return frame


# -----------------------------
# recognition_logs 欄位統一處理
# -----------------------------

def build_recognition_log(result, visit_time=None, leave_time=None, stay_minutes=None, visit_status=None, camera_id=DEFAULT_CAMERA_ID):
    """
    將 AI 辨識結果整理成 recognition_logs 資料表格式。

    recognition_logs 第四週欄位統一使用 stay_seconds；stay_minutes 僅供畫面顯示，不寫入資料庫。
    """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        # 辨識主體
        "subject_type": result.get(
            "subject_type",
            "unknown"
        ),
        "member_id": result.get("member_id"),
        "visitor_id": result.get("visitor_id"),
        "visitor_code": result.get("visitor_code"),
        
        # 顯示與會員相關欄位
        "name": result.get("name"),
        "vip": result.get("vip", False),
        "line_user_id": result.get("line_user_id"),
        
        # 辨識紀錄
        "camera_id": camera_id,
        "camera_location": result.get("camera_location", DEFAULT_CAMERA_LOCATION),
        "confidence": result.get("confidence", 0),
        "member_level": result.get(
            "member_level",
            "guest"
        ),
        "recognition_status": result.get(
            "recognition_status",
            "guest"
        ),
        "visit_status": visit_status,
        "recognized_at": now,
        "visit_time": visit_time,
        "last_seen_at": result.get("last_seen_at"),
        "leave_time": leave_time,
        "stay_seconds": result.get("stay_seconds", 0),
        "notification_sent": result.get("notification_sent", False),
        "coupon_sent": result.get("coupon_sent", False),
        "lottery_status": result.get("lottery_status", "not_joined"),
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
    print(
        f"subject_type: "
        f"{recognition_log['subject_type']}"
    )
    print(
        f"member_id: "
        f"{recognition_log['member_id']}"
    )
    print(
        f"visitor_id: "
        f"{recognition_log['visitor_id']}"
    )
    print(
        f"visitor_code: "
        f"{recognition_log['visitor_code']}"
    )
    print(
        f"camera_id: "
        f"{recognition_log['camera_id']}"
    )
    print(f"confidence: {recognition_log['confidence']}")
    print(f"member_level: {recognition_log['member_level']}")
    print(f"recognition_status: {recognition_log['recognition_status']}")
    print(f"visit_status: {recognition_log['visit_status']}")
    print(f"visit_time: {recognition_log['visit_time']}")
    print(f"leave_time: {recognition_log['leave_time']}")
    print(f"stay_seconds: {recognition_log['stay_seconds']}")
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
            stay_seconds=stay_seconds
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
