"""
AI 人臉偵測與會員比對服務

"""

import os
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import quote

import cv2
import numpy as np
from PIL import (
    Image,
    ImageOps,
    ImageDraw,
    ImageFont,
)

face_recognition = None
face_recognition_import_attempted = False
face_recognition_import_lock = threading.Lock()


def _get_face_recognition():
    """延遲載入 dlib/face_recognition，避免拖慢 Flask 啟動。"""
    global face_recognition
    global face_recognition_import_attempted

    if face_recognition is not None:
        return face_recognition

    with face_recognition_import_lock:
        if face_recognition is not None:
            return face_recognition
        if face_recognition_import_attempted:
            return None

        face_recognition_import_attempted = True
        try:
            import face_recognition as loaded_face_recognition
            face_recognition = loaded_face_recognition
        except ModuleNotFoundError:
            print(
                "警告：尚未安裝 face_recognition，"
                "AI 人臉辨識功能暫時無法使用"
            )

    return face_recognition

# MVP 階段仍先用圖片檔名找 fake_db 會員資料。
# 正式版會由資料庫同學提供 get_member_by_id(member_id)。
# 正式版不再使用 fake_db
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
        update_recognition_last_seen
        as db_update_recognition_last_seen,

        close_recognition_visit
        as db_close_recognition_visit,

        update_recognition_notification_sent
        as db_update_recognition_notification_sent
    )

except Exception as e:
    db_update_recognition_last_seen = None
    db_close_recognition_visit = None
    db_update_recognition_notification_sent = None

    print(
        f"警告：無法載入 recognition_logs 更新函式：{e}"
    )

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

FONT_CACHE = {}


def get_cached_font(font_size):
    """
    快取 Pillow 字型，避免每一幀都重新從硬碟載入。
    """

    if font_size not in FONT_CACHE:
        FONT_CACHE[font_size] = ImageFont.truetype(
            CHINESE_FONT_PATH,
            font_size
        )

    return FONT_CACHE[font_size]


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

        font = get_cached_font(font_size)

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


def is_path_within_directory(image_path, directory):
    """使用正規化絕對路徑確認圖片是否位於指定目錄內。"""
    if not image_path:
        return False

    try:
        normalized_path = os.path.normcase(
            os.path.abspath(image_path)
        )
        normalized_directory = os.path.normcase(
            os.path.abspath(directory)
        )

        return os.path.commonpath(
            [normalized_path, normalized_directory]
        ) == normalized_directory
    except (OSError, TypeError, ValueError):
        return False


def is_member_registration_face(member):
    """只接受明確存放於 member_images 的正式註冊人臉。"""
    return is_path_within_directory(
        member.get("image_path"),
        MEMBER_IMAGE_DIR
    )


# visitor_images 不存在時自動建立
os.makedirs(
    VISITOR_IMAGE_DIR,
    exist_ok=True
)

DEFAULT_CAMERA_ID = os.getenv("CAMERA_ID", "camera_1")
DEFAULT_CAMERA_LOCATION = os.getenv("CAMERA_LOCATION", "入口")

# 人臉距離越小代表越相似
# 使用 0.5 降低不同人物被誤認成會員的風險。
MEMBER_MATCH_TOLERANCE = 0.5

# 散客使用稍嚴格門檻，降低兩位陌生人被當成同一 visitor 的風險
VISITOR_MATCH_TOLERANCE = 0.55
VISITOR_REGISTRATION_MATCH_TOLERANCE = float(
    os.getenv("VISITOR_REGISTRATION_MATCH_TOLERANCE", "0.60")
)
VISITOR_REGISTRATION_MIN_SHARPNESS = float(
    os.getenv("VISITOR_REGISTRATION_MIN_SHARPNESS", "40")
)
VISITOR_REGISTRATION_MIN_FACE_SIZE = int(
    os.getenv("VISITOR_REGISTRATION_MIN_FACE_SIZE", "80")
)
RECENT_VISITOR_REGISTRATION_SECONDS = int(
    os.getenv("RECENT_VISITOR_REGISTRATION_SECONDS", "60")
)

# 保護會員與散客人臉快取的替換及快照讀取。
face_cache_lock = threading.RLock()
# Windows 上的 dlib 原生推論若同時由攝影機執行緒與 Flask 註冊請求
# 進入，可能直接造成 python.exe heap corruption，無法由 try/except
# 捕捉。所有 face_recognition 推論必須共用這把可重入鎖。
face_inference_lock = threading.RLock()


def _locked_face_locations(*args, **kwargs):
    with face_inference_lock:
        module = _get_face_recognition()
        if module is None:
            return []
        return face_recognition.face_locations(*args, **kwargs)


def _locked_face_encodings(*args, **kwargs):
    with face_inference_lock:
        module = _get_face_recognition()
        if module is None:
            return []
        return face_recognition.face_encodings(*args, **kwargs)


def _locked_face_distance(*args, **kwargs):
    with face_inference_lock:
        module = _get_face_recognition()
        if module is None:
            return np.array([])
        return face_recognition.face_distance(*args, **kwargs)

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
        "lottery_status": "not_joined",
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

    if _get_face_recognition() is None:
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
    
    max_dimension = 1000
    max_source_pixels = 80_000_000
    processed_image = None

    try:
        print("=" * 50)
        print("開始驗證會員照片")
        print("image_path:", image_path)
        print("file_size:", os.path.getsize(image_path), "bytes")
        
        with Image.open(image_path) as pil_image:
            source_width, source_height = pil_image.size
            source_pixels = source_width * source_height

            if source_pixels > max_source_pixels:
                return {
                    "success": False,
                    "message": (
                        "照片解析度過高，請改用較小尺寸的照片"
                    ),
                    "encoding": None,
                }

            # JPEG 先提示解碼器直接讀取較小版本，避免手機原圖在
            # 轉成 NumPy 前就占用數百 MB 記憶體。
            pil_image.draft(
                "RGB",
                (max_dimension, max_dimension),
            )
            pil_image.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )

            # 縮圖後再依 EXIF Orientation 轉正，避免複製完整原圖。
            pil_image = ImageOps.exif_transpose(pil_image)
            
            # 統一轉成 RGB，避免灰階、RGBA 等格式造成問題
            processed_image = pil_image.convert("RGB")
            
            # 轉成 face_recognition 可使用的 NumPy 陣列
            image = np.asarray(processed_image)
        
        print("標準化 image shape:", image.shape)
        
        height, width = image.shape[:2]
        image_for_detection = image
        
        print("偵測用 image shape:", image_for_detection.shape)
        
        face_locations_small = _locked_face_locations(
            image_for_detection,
            number_of_times_to_upsample=1,
            model="hog"
        )
        
        face_locations = list(face_locations_small)
        
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

    encodings = _locked_face_encodings(
        image,
        face_locations
    )

    if len(encodings) == 0:
        return {
            "success": False,
            "message": "無法建立人臉特徵",
            "encoding": None
        }

    # 辨識成功後以標準化尺寸覆寫上傳檔案，後台顯示、VIP 通知
    # 與之後的快取載入都不再使用高解析手機原圖。
    extension = os.path.splitext(image_path)[1].lower()
    image_format = "PNG" if extension == ".png" else "JPEG"
    temp_image_path = f"{image_path}.normalized"

    try:
        save_options = (
            {"optimize": True}
            if image_format == "PNG"
            else {"quality": 88, "optimize": True}
        )
        processed_image.save(
            temp_image_path,
            format=image_format,
            **save_options,
        )
        os.replace(temp_image_path, image_path)
    except Exception as e:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        print(f"標準化會員照片儲存失敗：{e}")
        return {
            "success": False,
            "message": "照片處理失敗，請重新上傳",
            "encoding": None,
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
    從正式資料庫讀取會員人臉 encoding。
    正式版不再使用 member_images 或 fake_db。
    """

    if _get_face_recognition() is None:
        print("尚未安裝 face_recognition，略過會員人臉資料載入")
        return None

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
                member_data["face_id"] = row.get("face_id")
                member_data["image_path"] = row.get("image_path")
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

            print("正式資料庫目前沒有可用的人臉資料")
            return members

        except Exception as e:
            print(f"正式資料庫會員人臉資料載入失敗：{e}")
            return None
    return None


def load_visitor_faces():
    """
    從正式資料庫載入既有散客的人臉 encoding。

    Flask 啟動時會執行此函式，
    因此即使程式重新啟動，
    仍能從 visitor_faces 重新取得散客人臉資料。
    """

    if _get_face_recognition() is None:
        print("尚未安裝 face_recognition，略過散客人臉資料載入")
        return None

    if get_all_visitor_faces is None:
        print("散客人臉資料函式尚未載入")
        return None

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
        return None



# 不在 Flask import 階段載入 dlib 或查詢人臉資料庫。
# Camera 串流啟動時會 reload；註冊防重與散客比對則按需載入。
known_members = []
known_visitors = []
recent_visitor_registrations = []


def reload_all_faces():
    """
    重新載入全部會員與散客人臉，兩邊都成功後才替換快取。

    任一資料來源載入失敗時會拋出例外，並保留原本快取，
    供 Reload Faces API 正確回傳失敗狀態。
    """

    new_members = load_member_faces()

    if new_members is None:
        raise RuntimeError("會員人臉資料載入失敗")

    new_visitors = load_visitor_faces()

    if new_visitors is None:
        raise RuntimeError("散客人臉資料載入失敗")

    with face_cache_lock:
        known_members[:] = new_members
        known_visitors[:] = new_visitors

    print(
        "全部人臉資料已重新載入："
        f"會員 {len(known_members)} 筆，"
        f"散客 {len(known_visitors)} 筆"
    )

    return known_members, known_visitors


def reload_member_faces():
    """
    重新載入會員人臉資料。

    新會員註冊完成後可以呼叫，
    讓攝影機不用重新啟動 app.py 就能辨識新會員。
    """

    new_data = load_member_faces()

    if new_data is None:
        print("會員人臉資料重新載入失敗，保留原本快取")
        with face_cache_lock:
            return known_members

    with face_cache_lock:
        known_members[:] = new_data

    print(
        f"會員人臉資料已重新載入，共 {len(known_members)} 筆"
    )

    return known_members

def refresh_member(member_id):
    """
    只更新指定會員的人臉與會員資料快取。
    不需要重新載入全部會員。
    """

    try:
        # 直接從資料庫取得這位會員最新資料
        member_data = db_get_member_by_id(member_id)

        if member_data is None:
            print(f"更新會員快取失敗：找不到 member_id={member_id}")
            return False

        updated_count = 0
        latest_member = normalize_member_data(member_data)

        with face_cache_lock:
            for index, old_member in enumerate(known_members):
                if old_member.get("member_id") != member_id:
                    continue

                new_member = dict(latest_member)
                new_member["face_id"] = old_member.get("face_id")
                new_member["image_path"] = old_member.get("image_path")
                new_member["encoding"] = old_member.get("encoding")
                known_members[index] = new_member
                updated_count += 1

        if updated_count:
            print("========== Member Cache Refreshed ==========")
            print(f"member_id: {member_id}")
            print(f"name: {latest_member.get('name')}")
            print(f"vip: {latest_member.get('vip')}")
            print(f"member_level: {latest_member.get('member_level')}")
            print(f"updated_face_count: {updated_count}")
            print("============================================")
            return True

        print(
            f"更新會員快取失敗："
            f"known_members 找不到 member_id={member_id}"
        )

        return False

    except Exception as e:
        print(f"更新會員快取失敗：{e}")
        return False


def remove_member_from_face_cache(member_id):
    """立即從會員人臉快取移除指定會員。"""
    with face_cache_lock:
        original_count = len(known_members)
        known_members[:] = [
            member
            for member in known_members
            if member.get("member_id") != member_id
        ]

        return original_count - len(known_members)


def sync_converted_visitor_cache(
    visitor_id,
    member_id,
    registration_encoding,
    registration_image_path
):
    """
    visitor 轉會員後原子同步兩份快取。

    完整 reload 正常時沿用資料庫載入結果；若新會員尚未出現在
    known_members，則使用已驗證的註冊 encoding 補入單筆快取。
    """
    try:
        member_data = db_get_member_by_id(member_id)

        if member_data is None:
            print(
                "散客轉會員快取同步失敗："
                f"找不到 member_id={member_id}"
            )
            return False

        normalized_member = normalize_member_data(member_data)
        encoding = np.array(
            registration_encoding,
            dtype=float
        )

        if encoding.shape != (128,):
            print(
                "散客轉會員快取同步失敗："
                f"encoding 維度={encoding.shape}"
            )
            return False

        with face_cache_lock:
            known_visitors[:] = [
                visitor
                for visitor in known_visitors
                if visitor.get("visitor_id") != visitor_id
            ]

            member_exists = any(
                member.get("member_id") == member_id
                for member in known_members
            )

            if not member_exists:
                cache_member = dict(normalized_member)
                cache_member["face_id"] = None
                cache_member["image_path"] = registration_image_path
                cache_member["encoding"] = encoding
                known_members.append(cache_member)

        print(
            "散客轉會員快取同步完成："
            f"visitor_id={visitor_id}，"
            f"member_id={member_id}，"
            f"member_exists={member_exists}"
        )
        return True

    except Exception as e:
        print(f"散客轉會員快取同步失敗：{e}")
        return False


def reload_visitor_faces():
    """
    重新載入散客人臉資料。

    新散客建立並寫入 visitor_faces 後呼叫，
    不需要重新啟動 Flask，
    就能立刻把新散客加入辨識名單。
    """

    new_data = load_visitor_faces()

    if new_data is None:
        print("散客人臉資料重新載入失敗，保留原本快取")
        with face_cache_lock:
            return known_visitors

    with face_cache_lock:
        known_visitors[:] = new_data

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


def register_new_visitor(frame, faces, encoding=None):
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

    if _get_face_recognition() is None:
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

    if (
        face_crop.shape[0] < VISITOR_REGISTRATION_MIN_FACE_SIZE
        or face_crop.shape[1] < VISITOR_REGISTRATION_MIN_FACE_SIZE
    ):
        print("散客建檔暫緩：臉部尺寸不足")
        return build_result(
            confidence=0,
            recognition_status="detecting"
        )

    grayscale_crop = cv2.cvtColor(
        face_crop,
        cv2.COLOR_BGR2GRAY
    )
    sharpness = float(
        cv2.Laplacian(
            grayscale_crop,
            cv2.CV_64F
        ).var()
    )

    if sharpness < VISITOR_REGISTRATION_MIN_SHARPNESS:
        print(
            "散客建檔暫緩：畫面清晰度不足，"
            f"sharpness={round(sharpness, 2)}"
        )
        return build_result(
            confidence=0,
            recognition_status="detecting"
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

    if encoding is None:
        try:
            encodings = _locked_face_encodings(
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
    else:
        try:
            current_encoding = np.asarray(
                encoding,
                dtype=float
            )
        except (TypeError, ValueError):
            return build_result(
                confidence=0,
                recognition_status="failed"
            )

    if len(current_encoding) != 128:
        print(
            "建立新散客失敗："
            f"encoding 維度為 {len(current_encoding)}"
        )

        return build_result(
            confidence=0,
            recognition_status="failed"
        )

    visitor_match = find_matching_visitor(
        current_encoding,
        tolerance=VISITOR_REGISTRATION_MATCH_TOLERANCE
    )

    if visitor_match.get("matched"):
        matched_visitor_id = visitor_match.get("visitor_id")

        with face_cache_lock:
            matched_visitor = next(
                (
                    dict(visitor)
                    for visitor in known_visitors
                    if visitor.get("visitor_id")
                    == matched_visitor_id
                ),
                None,
            )

        if matched_visitor is None:
            matched_visitor = {
                "visitor_id": matched_visitor_id,
                "visitor_code": visitor_match.get("visitor_code"),
                "display_name": visitor_match.get("visitor_code"),
            }

        print(
            "散客建檔前防重命中，沿用既有散客："
            f"visitor_id={matched_visitor_id}"
        )
        return build_result(
            visitor_data=matched_visitor,
            confidence=visitor_match.get("confidence", 0),
            recognition_status="recognized"
        )

    recent_cutoff = (
        time.monotonic()
        - RECENT_VISITOR_REGISTRATION_SECONDS
    )
    with face_cache_lock:
        recent_visitor_registrations[:] = [
            item
            for item in recent_visitor_registrations
            if item["created_at"] >= recent_cutoff
        ]
        recent_snapshot = list(recent_visitor_registrations)

    for recent in recent_snapshot:
        distance = float(
            _locked_face_distance(
                [recent["encoding"]],
                current_encoding
            )[0]
        )
        if distance >= VISITOR_REGISTRATION_MATCH_TOLERANCE:
            continue

        print(
            "散客建檔冷卻防重命中，沿用最近散客："
            f"visitor_id={recent['visitor'].get('visitor_id')}"
        )
        return build_result(
            visitor_data=recent["visitor"],
            confidence=round(max(0, 1 - distance), 2),
            recognition_status="recognized"
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

        visitor_data["encoding"] = np.array(
            current_encoding,
            dtype=float
        )

        with face_cache_lock:
            recent_visitor_registrations.append({
                "created_at": time.monotonic(),
                "encoding": np.array(
                    current_encoding,
                    dtype=float
                ),
                "visitor": dict(visitor_data),
            })

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


def check_duplicate_face(
    encoding,
    tolerance=MEMBER_MATCH_TOLERANCE,
    exclude_member_id=None
):
    """
    檢查上傳的人臉是否已存在於其他會員的人臉快取。

    更新會員照片時可傳入 exclude_member_id，避免把會員本人原有的
    encoding 判定成重複；新會員註冊不傳此參數時維持原本行為。

    回傳格式：
    {
        "is_duplicate": bool,
        "member_id": int | None,
        "name": str | None,
        "distance": float | None
    }
    """

    def log_result(member=None, distance=None):
        print(
            "會員人臉重複檢查："
            f"face_id={member.get('face_id') if member else None}，"
            f"image_path={member.get('image_path') if member else None}，"
            f"member_id={member.get('member_id') if member else None}，"
            f"distance={round(distance, 4) if distance is not None else None}，"
            f"threshold={tolerance}"
        )

    if _get_face_recognition() is None:
        log_result()
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    if encoding is None:
        log_result()
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
        log_result()
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    if encoding.shape != (128,):
        log_result()
        return {
            "is_duplicate": False,
            "member_id": None,
            "name": None,
            "distance": None
        }

    closest_member = None
    closest_distance = None

    # 註冊與刪除可能落在不同 Flask/Cloud Run instance。
    # 每次防重前都從共用資料庫同步，避免使用其他 instance
    # 尚未清掉的已刪除會員快取。
    reload_member_faces()

    with face_cache_lock:
        members_snapshot = [
            member
            for member in known_members
            if is_member_registration_face(member)
        ]

    for member in members_snapshot:
        if (
            exclude_member_id is not None
            and member.get("member_id") == exclude_member_id
        ):
            continue
        known_encoding = member.get("encoding")

        if known_encoding is None:
            continue

        distance = float(
            _locked_face_distance(
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
        closest_member_id = closest_member.get("member_id")

        # reload 若因短暫 DB 問題保留舊快取，命中後再確認一次
        # 正式會員是否仍存在。已刪除會員不可阻擋重新註冊。
        if (
            closest_member_id is not None
            and db_get_member_by_id is not None
        ):
            try:
                current_member = db_get_member_by_id(
                    closest_member_id
                )
            except Exception as e:
                print(
                    "會員人臉防重二次確認失敗："
                    f"member_id={closest_member_id}，error={e}"
                )
                current_member = closest_member

            if current_member is None:
                remove_member_from_face_cache(
                    closest_member_id
                )
                log_result()
                return {
                    "is_duplicate": False,
                    "member_id": None,
                    "name": None,
                    "distance": None,
                }

        log_result(closest_member, closest_distance)
        return {
            "is_duplicate": True,
            "member_id": closest_member_id,
            "name": closest_member.get("name"),
            "distance": round(closest_distance, 4)
        }

    log_result(closest_member, closest_distance)
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


def find_matching_visitor(
    encoding,
    tolerance=VISITOR_MATCH_TOLERANCE
):
    """
    將會員註冊照片的人臉 encoding，
    與目前尚未轉成會員的 known_visitors 比對。

    用途：
    Visitor → Member 散客轉正式會員。

    回傳格式：
    {
        "matched": bool,
        "visitor_id": int | None,
        "visitor_code": str | None,
        "distance": float | None,
        "confidence": float
    }
    """

    default_result = {
        "matched": False,
        "visitor_id": None,
        "visitor_code": None,
        "distance": None,
        "confidence": 0
    }

    if _get_face_recognition() is None:
        print(
            "散客轉會員比對失敗："
            "face_recognition 尚未載入"
        )
        return default_result

    if encoding is None:
        print(
            "散客轉會員比對失敗："
            "註冊照片 encoding 為空"
        )
        return default_result

    try:
        encoding = np.array(
            encoding,
            dtype=float
        )

    except (TypeError, ValueError) as e:
        print(
            "散客轉會員比對失敗："
            f"encoding 格式錯誤，原因：{e}"
        )
        return default_result

    if encoding.shape != (128,):
        print(
            "散客轉會員比對失敗："
            f"encoding 維度錯誤，目前為 {encoding.shape}"
        )
        return default_result

    closest_visitor = None
    closest_distance = None

    if not known_visitors:
        reload_visitor_faces()

    with face_cache_lock:
        visitors_snapshot = list(known_visitors)

    for visitor in visitors_snapshot:
        # 正常情況下，資料庫查詢已排除已轉會員散客。
        # 此處再補一層保護，避免快取中殘留舊資料。
        if visitor.get("converted_member_id") is not None:
            continue

        known_encoding = visitor.get("encoding")

        if known_encoding is None:
            continue

        try:
            known_encoding = np.array(
                known_encoding,
                dtype=float
            )
        except (TypeError, ValueError):
            continue

        if known_encoding.shape != (128,):
            continue

        distance = float(
            _locked_face_distance(
                [known_encoding],
                encoding
            )[0]
        )

        if (
            closest_distance is None
            or distance < closest_distance
        ):
            closest_distance = distance
            closest_visitor = visitor

    if (
        closest_visitor is not None
        and closest_distance is not None
        and closest_distance < tolerance
    ):
        confidence = max(
            0,
            min(1, 1 - closest_distance)
        )

        result = {
            "matched": True,
            "visitor_id": closest_visitor.get(
                "visitor_id"
            ),
            "visitor_code": closest_visitor.get(
                "visitor_code"
            ),
            "distance": round(
                closest_distance,
                4
            ),
            "confidence": round(
                confidence,
                4
            )
        }

        print(
            "========== Visitor Match Found =========="
        )
        print(
            "visitor_id:",
            result.get("visitor_id")
        )
        print(
            "visitor_code:",
            result.get("visitor_code")
        )
        print(
            "distance:",
            result.get("distance")
        )
        print(
            "tolerance:",
            tolerance
        )
        print(
            "========================================="
        )

        return result

    result = {
        **default_result,
        "distance": (
            round(closest_distance, 4)
            if closest_distance is not None
            else None
        )
    }

    print(
        "未找到符合的既有散客，"
        f"最近距離={result.get('distance')}，"
        f"門檻={tolerance}"
    )

    return result


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

    if _get_face_recognition() is None:
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
        detected_locations = _locked_face_locations(
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

    if _get_face_recognition() is None:
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
        encodings = _locked_face_encodings(
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

    with face_cache_lock:
        members_snapshot = list(known_members)
        visitors_snapshot = list(known_visitors)

    for member in members_snapshot:
        known_encoding = member.get("encoding")

        if known_encoding is None:
            continue

        member_encodings.append(known_encoding)
        valid_members.append(member)

    if member_encodings:
        member_distances = _locked_face_distance(
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

        if (
            member_best_distance < MEMBER_MATCH_TOLERANCE
            and member_confidence >= 0.5
        ):
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

    for visitor in visitors_snapshot:
        known_encoding = visitor.get("encoding")

        if known_encoding is None:
            continue

        visitor_encodings.append(known_encoding)
        valid_visitors.append(visitor)

    if visitor_encodings:
        visitor_distances = _locked_face_distance(
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

    guest_result = build_result(
        confidence=0,
        recognition_status="guest"
    )
    guest_result["_face_encoding"] = np.array(
        current_encoding,
        dtype=float
    )
    return guest_result

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
    
    if recognition_status == "no_face":
        display_name = "No Face"
        display_type = "No Face"
        box_label = ""

    elif recognition_status == "detecting":
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
    # 左上角英文與數字資訊
    # =============================

    text_color = (0, 255, 0)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    font_thickness = 2
    line_height = 32

    # Name 標題使用 OpenCV
    cv2.putText(
        frame,
        "Name:",
        (20, 40),
        font,
        font_scale,
        text_color,
        font_thickness,
        cv2.LINE_AA
    )

    # 姓名另外使用 Pillow，才能顯示中文
    frame = draw_chinese_text(
        frame,
        display_name,
        (105, 15),
        font_size=24,
        color=text_color
    )

    cv2.putText(
        frame,
        f"Type: {display_type}",
        (20, 40 + line_height),
        font,
        font_scale,
        text_color,
        font_thickness,
        cv2.LINE_AA
    )

    cv2.putText(
        frame,
        f"Confidence: {confidence}",
        (20, 40 + line_height * 2),
        font,
        font_scale,
        text_color,
        font_thickness,
        cv2.LINE_AA
    )

    if current_fps is not None:
        cv2.putText(
            frame,
            f"FPS: {current_fps:.1f}",
            (20, 40 + line_height * 3),
            font,
            font_scale,
            text_color,
            font_thickness,
            cv2.LINE_AA
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
        "lottery_status": (
            result.get("lottery_status")
            or "not_joined"
        ),
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

        return None


def send_line_notify(result, log_id=None):
    """
    發送 LINE VIP 到店通知。

    正確流程：
    1. 必須是正式會員
    2. 必須成功辨識
    3. 必須是 VIP
    4. 只有 arrived 才發送
    5. 同一次到店不可重複通知
    6. 先建立 vip_notifications pending
    7. 再執行 LINE 推播
    8. 最後更新 sent 或 failed
    """

    # -----------------------------------------
    # 1. 只處理正式會員
    # -----------------------------------------
    if result.get("subject_type") != "member":
        return None

    # -----------------------------------------
    # 2. 必須是成功辨識
    # -----------------------------------------
    if result.get("recognition_status") != "recognized":
        return None

    # -----------------------------------------
    # 3. 必須有正式會員 ID
    # -----------------------------------------
    member_id = result.get("member_id")

    if member_id is None:
        print("LINE 推播略過：member_id 不可為空")
        return None

    # -----------------------------------------
    # 4. 必須是 VIP 會員
    # member_level 與 vip 兩個欄位都要成立
    # -----------------------------------------
    if result.get("member_level") != "vip":
        return None

    if result.get("vip") is not True:
        return None

    # -----------------------------------------
    # 5. 店員通知不依賴會員本人的 LINE 綁定狀態
    # -----------------------------------------
    line_user_id = result.get("line_user_id")

    # -----------------------------------------
    # 6. 只有第一次到店 arrived 才發送
    # staying 與 left 都不發送
    # -----------------------------------------
    if result.get("visit_status") != "arrived":
        return None

    # -----------------------------------------
    # 7. 如果本次紀錄已通知過，不重複發送
    # -----------------------------------------
    if result.get("notification_sent") is True:
        return None

    # -----------------------------------------
    # 8. 必須有本次到店的 Recognition Log ID
    # log_id 是函式參數，由 visit_service 傳入
    # -----------------------------------------
    if log_id is None:
        print("LINE 推播略過：log_id 不可為空")
        return None

    name = result.get("name") or "VIP 會員"
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    face_image = result.get("face_image") or result.get("image_path")
    if (
        face_image
        and str(face_image).startswith("https://")
    ):
        result["notification_image_url"] = str(face_image)
    elif public_base_url and face_image:
        image_filename = os.path.basename(
            str(face_image).replace("\\", "/")
        )
        if image_filename:
            result["notification_image_url"] = (
                f"{public_base_url}/member_images/"
                f"{quote(image_filename)}"
            )

    if db_insert_vip_notification is None:
        print(
            "LINE 推播略過："
            "VIP 通知資料庫函式未成功匯入"
        )
        return None

    if notify_vip_recognition is None:
        print(
            "LINE 推播略過："
            "notify_vip_recognition 尚未成功匯入"
        )
        return None

    message = f"VIP會員 {name} 到店了！"

    try:
        # 先建立 pending 紀錄。
        # vip_notifications.log_id 為 UNIQUE，
        # 同一次到店不會重複建立通知。
        notification_id = db_insert_vip_notification(
            member_id=member_id,
            log_id=log_id,
            line_user_id=line_user_id,
            message=message,
            status="pending",
            notification_type="vip",
            retry_count=0,
            response_message=None
        )

        if notification_id is None:
            print(
                "========== VIP Notification Skipped =========="
            )
            print(f"log_id: {log_id}")
            print("原因：同一次到店通知已存在，不重複推播")
            print(
                "=============================================="
            )

            # 代表這筆到店紀錄已經有通知資料。
            result["notification_sent"] = True

            return "duplicate"

        # 真正呼叫 LINE 推播
        status = notify_vip_recognition(result)

        sent_at = None

        if status == "sent":
            notification_status = "sent"

            sent_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            # 更新 AI 記憶體中的通知狀態
            result["notification_sent"] = True

            # 更新 recognition_logs.notification_sent
            if db_update_recognition_notification_sent is not None:
                try:
                    updated_rows = (
                        db_update_recognition_notification_sent(
                            log_id=log_id,
                            notification_sent=True
                        )
                    )

                    print(
                        "recognition_logs notification_sent "
                        f"更新完成：log_id={log_id}，"
                        f"updated_rows={updated_rows}"
                    )

                except Exception as e:
                    print(
                        "recognition_logs notification_sent "
                        f"更新失敗：log_id={log_id}，"
                        f"error={e}"
                    )

        else:
            notification_status = "failed"
            result["notification_sent"] = False

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
        print(
            f"LINE notify status: "
            f"{notification_status}"
        )
        print("=======================================")

        return notification_status

    except Exception as e:
        result["notification_sent"] = False

        print(
            "========== LINE Notification Failed =========="
        )
        print(f"log_id: {log_id}")
        print(f"VIP 會員到店：{name}")
        print(f"member_id: {member_id}")
        print(f"LINE notify error: {e}")
        print(
            "=============================================="
        )

        return "failed"
