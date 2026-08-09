import os
import json
import random
import secrets
import threading
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv


load_dotenv()


# 辨識狀態
RECOGNITION_STATUS_RECOGNIZED = "recognized"
RECOGNITION_STATUS_GUEST = "guest"
RECOGNITION_STATUS_FAILED = "failed"
RECOGNITION_STATUS_NO_FACE = "no_face"

# 到店狀態
VISIT_STATUS_ARRIVED = "arrived"
VISIT_STATUS_STAYING = "staying"
VISIT_STATUS_LEFT = "left"




def get_member_level_text(member_level):
    level_text_map = {
        "vip": "VIP 會員",
        "normal": "一般會員",
        "guest": "陌生客"
    }

    return level_text_map.get(member_level, "未知")


# 抽獎活動設定
LOTTERY_CAMPAIGN_CODE = "WELCOME_2026"
REGISTRATION_WELCOME_COUPON_SOURCE = "registration_welcome"
REGISTRATION_WELCOME_COUPON_NAME = "新會員 100 元註冊禮"

LOTTERY_PRIZE_DISPLAY_NAMES = {
    "WELCOME_50": "$50 折價券",
    "WELCOME_10_OFF": "9 折優惠",
    "WELCOME_200": "$200 折價券",
    "WELCOME_GIFT": "小禮品",
    "WELCOME_FREE_SHIP": "免運券",
    "WELCOME_RETRY": "再抽一次",
}
# 迎新禮、生日禮與 VIP 禮遇設定
REGISTRATION_WELCOME_COUPON_SOURCE = "registration_welcome"
REGISTRATION_WELCOME_COUPON_NAME = "新會員 100 元註冊禮"

BIRTHDAY_COUPON_SOURCE_PREFIX = "birthday_"
BIRTHDAY_COUPON_NAME = "生日禮 200 元優惠券"

VIP_BENEFIT_CODE = "VIP_DISCOUNT_5"
VIP_MEMBER_LEVEL = "vip"
VIP_DISCOUNT_PERCENT = Decimal("5.00")


def get_lottery_prize_display_name(prize_code, fallback=None):
    return (
        LOTTERY_PRIZE_DISPLAY_NAMES.get(prize_code)
        or fallback
        or prize_code
        or "獎品"
    )


REDEMPTION_BASE_URL = os.getenv(
    "REDEMPTION_BASE_URL",
    os.getenv(
        "PUBLIC_BASE_URL",
        "http://127.0.0.1:5000",
    ),
).rstrip("/")

LOTTERY_REDEMPTION_DAYS = int(
    os.getenv(
        "LOTTERY_REDEMPTION_DAYS",
        "30"
    )
)

# VIP 通知狀態
NOTIFICATION_STATUS_PENDING = "pending"
NOTIFICATION_STATUS_SENT = "sent"
NOTIFICATION_STATUS_FAILED = "failed"


def clean_env(value):
    if value is None:
        return None
    return value.replace('"', '').replace("'", "")

def to_bool(value):
    """
    將前端、LINE 或 API 傳來的值安全轉成布林值。
    """

    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "on"
        }

    return bool(value)

def normalize_encoding_data(encoding_data):
    """
    將人臉 encoding 統一轉成合法的 128 維 JSON 字串。
    """

    if encoding_data is None:
        raise ValueError("encoding_data 不可為空")

    if hasattr(encoding_data, "tolist"):
        encoding_data = encoding_data.tolist()

    if isinstance(encoding_data, str):
        try:
            encoding_data = json.loads(encoding_data)
        except json.JSONDecodeError as e:
            raise ValueError(
                "encoding_data 不是合法 JSON"
            ) from e

    if not isinstance(encoding_data, (list, tuple)):
        raise ValueError(
            "encoding_data 必須是 list、tuple、NumPy array 或 JSON 字串"
        )

    if len(encoding_data) != 128:
        raise ValueError(
            f"encoding_data 必須是 128 維，"
            f"目前為 {len(encoding_data)} 維"
        )

    try:
        encoding_data = [
            float(value)
            for value in encoding_data
        ]
    except (TypeError, ValueError) as e:
        raise ValueError(
            "encoding_data 的每一項都必須是數字"
        ) from e

    return json.dumps(
        encoding_data,
        ensure_ascii=False
    )

_connection_pool = None
_connection_pool_lock = threading.Lock()


def _get_connection_config():
    config = {
        "user": clean_env(os.getenv("DB_USER", "root")),
        "password": clean_env(os.getenv("DB_PASSWORD", "")),
        "database": clean_env(
            os.getenv("DB_NAME", "smart_member_system")
        ),
        "connection_timeout": int(
            clean_env(os.getenv("DB_CONNECTION_TIMEOUT", "10"))
        ),

        # 新增這兩行
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }

    instance_connection_name = clean_env(
        os.getenv("INSTANCE_CONNECTION_NAME")
    )

    if instance_connection_name:
        config["unix_socket"] = (
            f"/cloudsql/{instance_connection_name}"
        )
    else:
        config["host"] = clean_env(
            os.getenv("DB_HOST", "localhost")
        )
        config["port"] = int(
            clean_env(os.getenv("DB_PORT", "3306"))
        )

    return config


def get_connection():
    """
    透過連線池重用雲端 MySQL 連線。

    測試或特殊環境可設定 DB_POOL_ENABLED=false，
    回到每次建立獨立連線的行為。
    """
    global _connection_pool

    config = _get_connection_config()
    if not to_bool(os.getenv("DB_POOL_ENABLED", "true")):
        return mysql.connector.connect(**config)

    if _connection_pool is None:
        with _connection_pool_lock:
            if _connection_pool is None:
                _connection_pool = pooling.MySQLConnectionPool(
                    pool_name=f"smart_member_{os.getpid()}",
                    pool_size=max(
                        int(os.getenv("DB_POOL_SIZE", "5")),
                        1,
                    ),
                    pool_reset_session=True,
                    **config,
                )

    return _connection_pool.get_connection()


def get_all_members():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            member_id,
            name,
            phone,
            birthday,       
            vip,
            member_level,
            total_visit_count,
            last_visit_time,
            total_visit_time,
            updated_by,
            line_user_id,
            total_amount,
            favorite_product,
            face_image,
            registration_source,
            created_at,
            updated_at
        FROM members
    """)

    members = cursor.fetchall()

    for member in members:
        member["member_level_text"] = get_member_level_text(
            member.get("member_level")
        )

    cursor.close()
    conn.close()

    return members

def get_member_by_id(member_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            member_id,
            name,
            phone,
            birthday,
            vip,
            member_level,
            total_visit_count,
            last_visit_time,
            total_visit_time,
            updated_by,
            line_user_id,
            total_amount,
            favorite_product,
            face_image,
            registration_source,
            created_at,
            updated_at
        FROM members
        WHERE member_id = %s
        """,
        (member_id,)
    )

    member = cursor.fetchone()

    if member:
        member["member_level_text"] = get_member_level_text(
            member.get("member_level")
        )

    cursor.close()
    conn.close()

    return member


def get_member_preferences(member_id):
    """取得會員註冊時在 LINE 勾選的喜好類別清單（member_preferences 表），依寫入順序排列。"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT preference_value
            FROM member_preferences
            WHERE member_id = %s
            ORDER BY preference_id
            """,
            (member_id,)
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def issue_registration_welcome_coupon(member_id):
    """發送一次性的 100 元註冊禮；重複呼叫會沿用原券。"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id FROM members WHERE member_id = %s FOR UPDATE",
            (member_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError("找不到要發送註冊禮的會員")

        cursor.execute(
            "SELECT coupon_id FROM coupons "
            "WHERE coupon_name = %s AND status = 'active' LIMIT 1",
            (REGISTRATION_WELCOME_COUPON_NAME,),
        )
        coupon = cursor.fetchone()
        if coupon is None:
            raise RuntimeError("尚未建立新會員 100 元註冊禮，請先執行資料庫 migration")

        cursor.execute(
            "SELECT member_coupon_id FROM member_coupons "
            "WHERE member_id = %s AND source = %s LIMIT 1",
            (member_id, REGISTRATION_WELCOME_COUPON_SOURCE),
        )
        existing = cursor.fetchone()
        if existing is not None:
            conn.commit()
            return {
                "member_coupon_id": existing["member_coupon_id"],
                "issued": False,
            }

        cursor.execute(
            "INSERT INTO member_coupons "
            "(member_id, coupon_id, source, status, receive_time, used_time) "
            "VALUES (%s, %s, %s, 'unused', NOW(), NULL)",
            (
                member_id,
                coupon["coupon_id"],
                REGISTRATION_WELCOME_COUPON_SOURCE,
            ),
        )
        member_coupon_id = cursor.lastrowid
        conn.commit()
        return {"member_coupon_id": member_coupon_id, "issued": True}
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def redeem_member_coupon(member_coupon_id, member_id):
    """由已驗證的會員本人將一張可用優惠券核銷為已使用。"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT mc.member_coupon_id, mc.status, mc.source,
                   c.coupon_name, c.status AS coupon_status,
                   c.start_at, c.end_at
            FROM member_coupons AS mc
            JOIN coupons AS c ON c.coupon_id = mc.coupon_id
            WHERE mc.member_coupon_id = %s AND mc.member_id = %s
            FOR UPDATE
            """,
            (member_coupon_id, member_id),
        )
        coupon = cursor.fetchone()
        if coupon is None:
            conn.rollback()
            return {"success": False, "message": "找不到這張優惠券"}
        if coupon.get("source") != REGISTRATION_WELCOME_COUPON_SOURCE:
            conn.rollback()
            return {"success": False, "message": "這張優惠券不支援按鈕兌換"}
        if coupon.get("status") == "used":
            conn.rollback()
            return {"success": False, "message": "這張優惠券已經兌換"}
        if coupon.get("status") != "unused" or coupon.get("coupon_status") != "active":
            conn.rollback()
            return {"success": False, "message": "這張優惠券目前無法兌換"}

        now = datetime.now()
        if coupon.get("start_at") and coupon["start_at"] > now:
            conn.rollback()
            return {"success": False, "message": "這張優惠券尚未生效"}
        if coupon.get("end_at") and coupon["end_at"] < now:
            conn.rollback()
            return {"success": False, "message": "這張優惠券已經過期"}

        cursor.execute(
            "UPDATE member_coupons SET status = 'used', used_time = NOW() "
            "WHERE member_coupon_id = %s AND member_id = %s AND status = 'unused'",
            (member_coupon_id, member_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("優惠券核銷狀態更新失敗")
        conn.commit()
        return {
            "success": True,
            "message": "100 元折價券兌換成功",
            "member_coupon_id": member_coupon_id,
        }
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def insert_recognition_log(
    subject_type=None,
    member_id=None,
    visitor_id=None,
    visitor_code=None,
    name=None,
    vip=False,
    line_user_id=None,
    confidence=0,
    recognized_at=None,
    camera_location=None,
    camera_id=None,
    member_level=None,
    recognition_status=RECOGNITION_STATUS_RECOGNIZED,
    visit_status=VISIT_STATUS_ARRIVED,
    visit_time=None,
    last_seen_at=None,
    leave_time=None,
    stay_seconds=0,
    notification_sent=False,
    coupon_sent=False,
    lottery_status="not_joined",
    created_at=None
):

    conn = None
    cursor = None

    try:
        # 如果沒有 member_id，視為 Guest
        if subject_type is None:
            if member_id is not None:
                subject_type = "member"
            elif visitor_id is not None:
                subject_type = "visitor"
            else:
                subject_type = "unknown"

        valid_subject_types = {
            "member",
            "visitor",
            "unknown"
        }

        if subject_type not in valid_subject_types:
            raise ValueError(
                f"不支援的 subject_type：{subject_type}"
            )

        if subject_type == "member":
            if member_id is None:
                raise ValueError(
                    "subject_type 為 member 時，member_id 不可為空"
                )

            visitor_id = None
            visitor_code = None

        elif subject_type == "visitor":
            if visitor_id is None:
                raise ValueError(
                    "subject_type 為 visitor 時，visitor_id 不可為空"
                )

            member_id = None
            line_user_id = None
            vip = False
            member_level = "guest"

            if name is None:
                name = visitor_code or "Visitor"

        else:
            member_id = None
            visitor_id = None
            visitor_code = None
            line_user_id = None
            vip = False
            member_level = "guest"

            if name is None:
                name = "Guest"

            if recognition_status == RECOGNITION_STATUS_RECOGNIZED:
                recognition_status = RECOGNITION_STATUS_GUEST
        
        # 1. 檢查 recognition_status 是否合法
        valid_recognition_statuses = {
            RECOGNITION_STATUS_RECOGNIZED,
            RECOGNITION_STATUS_GUEST,
            RECOGNITION_STATUS_FAILED,
            RECOGNITION_STATUS_NO_FACE
        }

        # 2. 檢查 visit_status 是否合法
        valid_visit_statuses = {
            VISIT_STATUS_ARRIVED,
            VISIT_STATUS_STAYING,
            VISIT_STATUS_LEFT,
        }

        if recognition_status not in valid_recognition_statuses:
            raise ValueError(
                f"不支援的 recognition_status：{recognition_status}"
            )

        if visit_status not in valid_visit_statuses:
            raise ValueError(
                f"不支援的 visit_status：{visit_status}"
            )
        
        if recognition_status == RECOGNITION_STATUS_NO_FACE:
            raise ValueError(
                "no_face 不應建立 recognition_logs 到店紀錄"
            )

        # 3. 沒有傳時間時，自動補現在時間
        if recognized_at is None:
            recognized_at = datetime.now()

        if created_at is None:
            created_at = datetime.now()

        if visit_time is None:
            visit_time = recognized_at

        if last_seen_at is None:
            last_seen_at = visit_time

        # 4. 檢查通過後，才連線資料庫
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO recognition_logs (
            subject_type,
            member_id,
            visitor_id,
            visitor_code,
            camera_id,
            name,
            vip,
            line_user_id,
            confidence,
            member_level,
            recognition_status,
            visit_status,
            visit_time,
            last_seen_at,
            leave_time,
            stay_seconds,
            notification_sent,
            coupon_sent,
            lottery_status,
            recognized_at,
            created_at,
            camera_location
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        data = (
            subject_type,
            member_id,
            visitor_id,
            visitor_code,
            camera_id,
            name,
            vip,
            line_user_id,
            confidence,
            member_level,
            recognition_status,
            visit_status,
            visit_time,
            last_seen_at,
            leave_time,
            stay_seconds,
            to_bool(notification_sent),
            to_bool(coupon_sent),
            lottery_status,
            recognized_at,
            created_at,
            camera_location
        )

        cursor.execute(sql, data)
        conn.commit()

        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增 recognition_logs 失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_recognition_log(data):
    return insert_recognition_log(
        subject_type=data.get("subject_type"),
        member_id=data.get("member_id"),
        visitor_id=data.get("visitor_id"),
        visitor_code=data.get("visitor_code"),
        name=data.get("name"),
        vip=data.get("vip", False),
        line_user_id=data.get("line_user_id"),
        confidence=data.get("confidence", 0),
        recognized_at=data.get("recognized_at") or data.get("recognition_time"),
        camera_location=data.get("camera_location"),

        camera_id=data.get("camera_id"),
        member_level=data.get("member_level"),
        recognition_status=(
            data.get("recognition_status")
            or RECOGNITION_STATUS_RECOGNIZED
        ),
        visit_status=(
            data.get("visit_status")
            or VISIT_STATUS_ARRIVED
        ),
        visit_time=data.get("visit_time" ),
        last_seen_at=data.get("last_seen_at"),
        leave_time=data.get("leave_time"),
        stay_seconds=data.get("stay_seconds", 0),
        notification_sent=data.get(
            "notification_sent",
            False
        ),
        coupon_sent=data.get(
            "coupon_sent",
            False
        ),
        lottery_status=(
            data.get("lottery_status")
            or "not_joined"
        ),

    )


def insert_vip_notification(
    member_id,
    log_id,
    line_user_id,
    message,
    status="pending",
    notification_type="vip",
    retry_count=0,
    response_message=None
):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO vip_notifications (
            member_id,
            log_id,
            line_user_id,
            message,
            status,
            notification_type,
            retry_count,
            response_message
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        data = (
            member_id,
            log_id,
            line_user_id,
            message,
            status,
            notification_type,
            retry_count,
            response_message
            
        )

        cursor.execute(sql, data)
        conn.commit()

        return cursor.lastrowid

    except mysql.connector.IntegrityError as e:
        if conn:
            conn.rollback()

        # 1062：同一個 log_id 已經有通知。成功或仍在處理中的
        # 紀錄不重送；先前發送失敗的紀錄則重新標成 pending，
        # 讓 Camera 下一次恢復同一筆 visit 時可以重試。
        if e.errno == 1062:
            retry_cursor = conn.cursor(dictionary=True)
            retry_cursor.execute(
                """
                SELECT notification_id, status
                FROM vip_notifications
                WHERE log_id = %s
                FOR UPDATE
                """,
                (log_id,),
            )
            existing = retry_cursor.fetchone()

            if (
                existing is not None
                and existing.get("status") == NOTIFICATION_STATUS_FAILED
            ):
                retry_cursor.execute(
                    """
                    UPDATE vip_notifications
                    SET
                        status = %s,
                        retry_count = retry_count + 1,
                        response_message = NULL
                    WHERE notification_id = %s
                      AND status = %s
                    """,
                    (
                        NOTIFICATION_STATUS_PENDING,
                        existing["notification_id"],
                        NOTIFICATION_STATUS_FAILED,
                    ),
                )
                conn.commit()
                notification_id = existing["notification_id"]
                retry_cursor.close()
                return notification_id

            retry_cursor.close()
            print(
                f"VIP 通知已存在，略過重複新增：log_id={log_id}"
            )
            return None

        print("新增 vip_notifications 失敗：", e)
        raise

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增 vip_notifications 失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def update_vip_notification_status(
    notification_id,
    status,
    sent_at=None
):
    """
    更新 VIP 通知結果。

    status:
    - pending：尚未發送
    - sent：發送成功
    - failed：發送失敗
    """

    conn = None
    cursor = None

    try:
        if notification_id is None:
            raise ValueError("notification_id 不可為空")

        if status not in (
            NOTIFICATION_STATUS_PENDING,
            NOTIFICATION_STATUS_SENT,
            NOTIFICATION_STATUS_FAILED
        ):
            raise ValueError(
                f"不支援的 VIP 通知狀態：{status}"
            )

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        UPDATE vip_notifications
        SET
            status = %s,
            sent_at = %s
        WHERE notification_id = %s
        """

        cursor.execute(
            sql,
            (
                status,
                sent_at,
                notification_id
            )
        )

        conn.commit()

        return cursor.rowcount

    except Exception as e:
        if conn:
            conn.rollback()

        print("更新 vip_notifications 狀態失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def get_active_visit(
    subject_type,
    subject_id,
    camera_id=None
):
    """
    查詢指定會員或散客目前尚未結束的到店紀錄。

    支援：
    - subject_type = "member"
      使用 member_id 查詢

    - subject_type = "visitor"
      使用 visitor_id 查詢

    只查詢：
    - leave_time IS NULL
    - visit_status 為 arrived 或 staying
    - subject_type 必須一致
    - 有傳 camera_id 時，只查指定攝影機

    回傳：
    - 找到時回傳 recognition_logs 字典
    - 找不到或參數不合法時回傳 None
    """

    conn = None
    cursor = None

    try:
        # 依辨識對象類型決定查詢欄位
        if subject_type == "member":
            id_column = "member_id"

        elif subject_type == "visitor":
            id_column = "visitor_id"

        else:
            return None

        if subject_id is None:
            return None

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # id_column 只會由上方固定選擇 member_id 或 visitor_id，
        # 不直接接受外部輸入，因此可安全放入 SQL。
        sql = f"""
        SELECT
            log_id,
            subject_type,
            member_id,
            visitor_id,
            visitor_code,
            camera_id,
            name,
            vip,
            line_user_id,
            confidence,
            member_level,
            recognition_status,
            visit_status,
            recognized_at,
            visit_time,
            last_seen_at,
            leave_time,
            stay_seconds,    
            notification_sent,
            camera_location,
            created_at
        FROM recognition_logs
        WHERE subject_type = %s
          AND {id_column} = %s
          AND leave_time IS NULL
          AND visit_status IN (%s, %s)
        """

        params = [
            subject_type,
            subject_id,
            VISIT_STATUS_ARRIVED,
            VISIT_STATUS_STAYING
        ]

        # 有指定攝影機時，只恢復該攝影機的 active visit
        if camera_id:
            sql += """
              AND camera_id = %s
            """
            params.append(camera_id)

        sql += """
        ORDER BY visit_time DESC, log_id DESC
        LIMIT 1
        """

        cursor.execute(sql, tuple(params))
        return cursor.fetchone()

    except Exception as e:
        print(
            "查詢 active visit 失敗："
            f"subject_type={subject_type}, "
            f"subject_id={subject_id}, "
            f"camera_id={camera_id}, "
            f"error={e}"
        )
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def update_recognition_last_seen(log_id, last_seen_at):
    conn = None
    cursor = None
            
    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        UPDATE recognition_logs
        SET
            last_seen_at = %s,
            recognition_status = %s,
            visit_status = %s
        WHERE log_id = %s
          AND leave_time IS NULL
          AND visit_status IN (%s, %s)
        """

        cursor.execute(
            sql,
            (
                last_seen_at,
                RECOGNITION_STATUS_RECOGNIZED,
                VISIT_STATUS_STAYING,
                log_id,
                VISIT_STATUS_ARRIVED,
                VISIT_STATUS_STAYING,
            )
        )

        conn.commit()
        return cursor.rowcount

    except Exception as e:
        if conn:
            conn.rollback()

        print("更新 recognition_logs last_seen_at 失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

def update_recognition_notification_sent(
    log_id,
    notification_sent=True
):
    """
    更新 recognition_logs 的 VIP 通知發送狀態。

    notification_sent:
    - True：LINE 通知已成功發送
    - False：LINE 通知尚未成功發送
    """

    conn = None
    cursor = None

    try:
        if log_id is None:
            raise ValueError("log_id 不可為空")

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        UPDATE recognition_logs
        SET notification_sent = %s
        WHERE log_id = %s
        """

        cursor.execute(
            sql,
            (
                to_bool(notification_sent),
                log_id
            )
        )

        conn.commit()

        return cursor.rowcount

    except Exception as e:
        if conn:
            conn.rollback()

        print(
            "更新 recognition_logs.notification_sent 失敗：",
            e
        )

        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def close_recognition_visit(
    log_id,
    last_seen_at,
    leave_time,
    stay_seconds,
):
    conn = None
    cursor = None

    try:
        if log_id is None:
            raise ValueError("log_id 不可為空")

        if last_seen_at is None:
            raise ValueError("last_seen_at 不可為空")

        if leave_time is None:
            raise ValueError("leave_time 不可為空")

        stay_seconds = max(
            0,
            int(stay_seconds or 0)
        )

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        UPDATE recognition_logs
        SET
            recognition_status = %s,
            visit_status = %s,
            last_seen_at = %s,
            leave_time = %s,
            stay_seconds = %s
        WHERE log_id = %s
          AND leave_time IS NULL
          AND visit_status IN (%s, %s)
        """

        cursor.execute(
            sql,
            (
                RECOGNITION_STATUS_RECOGNIZED,
                VISIT_STATUS_LEFT,
                last_seen_at,
                leave_time,
                stay_seconds,
                log_id,
                VISIT_STATUS_ARRIVED,
                VISIT_STATUS_STAYING
            )
        )

        closed_count = cursor.rowcount

        if closed_count == 1:
            cursor.execute(
                """
                SELECT
                    subject_type,
                    member_id,                
                    visitor_id
                FROM recognition_logs
                 WHERE log_id = %s
                """,
                (log_id,)
            )

            subject = cursor.fetchone()

            if subject:
                subject_type = subject[0]
                member_id = subject[1]
                visitor_id = subject[2]

                if (
                    subject_type == "member"
                    and member_id is not None
                ):
                    
                    cursor.execute(
                        """
                        UPDATE members
                        SET
                            total_visit_count =
                                COALESCE(total_visit_count, 0) + 1,
                            total_visit_time =
                                COALESCE(total_visit_time, 0) + %s,
                            last_visit_time = %s,
                            updated_by = 'system'
                        WHERE member_id = %s
                        """,
                        (
                            stay_seconds,
                            leave_time,
                            member_id
                        )
                    )

                elif (
                    subject_type == "visitor"
                    and visitor_id is not None
                ):
                    cursor.execute(
                        """
                        UPDATE visitors
                        SET
                            visitor_visit_count =
                                COALESCE(visitor_visit_count, 0) + 1,                           
                            last_seen_at = %s
                        WHERE visitor_id = %s
                        """,
                        (
                            last_seen_at,
                            visitor_id
                        )
                    )

        conn.commit()
        return closed_count



    except Exception as e:
        if conn:
            conn.rollback()

        print("更新離店紀錄失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


def insert_member(
    name,
    phone=None,
    birthday=None,
    vip=False,
    member_level="normal",
    total_visit_count=0,
    line_user_id=None,
    total_amount=0,
    favorite_product=None,
    face_image=None,
    registration_source="line"
):
    conn = None
    cursor = None

    try:
        vip = to_bool(vip)
        member_level = "vip" if vip else "normal"

        total_visit_count = int(total_visit_count or 0)
        total_amount = float(total_amount or 0)

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
    INSERT INTO members (
        name,
        phone,
        birthday,
        vip,
        member_level,
        total_visit_count,
        line_user_id,
        total_amount,
        favorite_product,
        face_image,
        registration_source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

        cursor.execute(
            sql,
            (
                name,
                phone,
                birthday,
                vip,
                member_level,
                total_visit_count,
                line_user_id,
                total_amount,
                favorite_product,
                face_image,
                registration_source
            )
        )

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增會員失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

            
def insert_face_image(member_id, image_path, encoding_data):
    conn = None
    cursor = None

    try:
        if member_id is None:
            raise ValueError("member_id 不可為空")

        encoding_data = normalize_encoding_data(
    encoding_data
        )
        
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO face_images (
            member_id,
            image_path,
            encoding_data
        )
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            sql,
            (
                member_id,
                image_path,
                encoding_data
            )
        )

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增人臉資料失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

def register_member_with_face(
    name,
    phone=None,
    birthday=None,
    vip=False,
    member_level="normal",
    total_visit_count=0,
    last_visit_time=None,
    total_visit_time=0,
    updated_by="system",
    line_user_id=None,
    total_amount=0,
    favorite_product=None,
    face_image=None,
    registration_source="line",
    image_path=None,
    encoding_data=None
):
    conn = None
    cursor = None

    try:
        if not name:
            raise ValueError("name 不可為空")

        if not image_path:
            raise ValueError("image_path 不可為空")

        if encoding_data is None:
            raise ValueError("encoding_data 不可為空")

        vip = to_bool(vip)
        member_level = "vip" if vip else "normal"

        total_visit_count = int(total_visit_count or 0)
        total_visit_time = int(total_visit_time or 0)
        total_amount = float(total_amount or 0)

        encoding_data = normalize_encoding_data(
            encoding_data
        )

        if not face_image:
            face_image = image_path

        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor()



        # 第一步：新增會員
        member_sql = """
        INSERT INTO members (
            name,
            phone,
            birthday,
            vip,
            member_level,
            total_visit_count,
            last_visit_time,
            total_visit_time,
            updated_by,
            line_user_id,
            total_amount,
            favorite_product,
            face_image,
            registration_source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            member_sql,
            (
                name,
                phone,
                birthday,
                vip,
                member_level,
                total_visit_count,
                last_visit_time,
                total_visit_time,
                updated_by,
                line_user_id,
                total_amount,
                favorite_product,
                face_image,
                registration_source
            )
        )

        member_id = cursor.lastrowid

        # 第二步：新增人臉資料
        face_sql = """
        INSERT INTO face_images (
            member_id,
            image_path,
            encoding_data
        )
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            face_sql,
            (
                member_id,
                image_path,
                encoding_data
            )
        )

        face_id = cursor.lastrowid

        if face_id is None:
            raise RuntimeError("新增人臉資料後未取得 face_id")

        # 會員與人臉都成功，才一起提交
        conn.commit()

        return {
            "member_id": member_id,
            "face_id": face_id,
            "success": True
        }

    except Exception as e:
        if conn:
            conn.rollback()

        print("會員與人臉資料註冊失敗，已 rollback：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

def convert_visitor_to_member(
    visitor_id,
    name,
    phone=None,
    birthday=None,
    vip=False,
    member_level="normal",
    line_user_id=None,
    registration_source="line_visitor_conversion",
    registration_image_path=None,
    registration_encoding=None,
    display_face_image=None,
    updated_by=None,
    total_amount=0,
    favorite_product=None,
    active_visit_timeout_seconds=60,
):
    """
    將既有散客轉成正式會員。

    同一個 transaction 內完成：
    1. 建立 members
    2. 複製 visitor_faces 至 face_images
    3. 寫入本次註冊照片
    4. 更新 visitors.converted_member_id
    5. 將尚未離店的 visitor 紀錄切換成 member
    """
    normalized_registration_encoding = None

    if registration_encoding is not None:
        normalized_registration_encoding = normalize_encoding_data(
            registration_encoding
        )

    registration_face_filename = None

    if display_face_image:
        registration_face_filename = display_face_image
    elif registration_image_path:
        registration_face_filename = registration_image_path
    
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. 鎖定 visitor，避免重複轉換
        cursor.execute(
            """
            SELECT
                visitor_id,
                visitor_code,
                converted_member_id,
                visitor_visit_count,
                last_seen_at
            FROM visitors
            WHERE visitor_id = %s
            FOR UPDATE
            """,
            (visitor_id,)
        )

        visitor = cursor.fetchone()

        if not visitor:
            raise ValueError("找不到指定的 visitor")

        if visitor.get("converted_member_id") is not None:
            raise ValueError("此 visitor 已經轉成正式會員")

        # 2. 建立 members
        cursor.execute(
            """
            INSERT INTO members (
                name,
                phone,
                birthday,
                vip,
                member_level,
                total_visit_count,
                line_user_id,
                registration_source,
                last_visit_time,
                face_image,
                updated_by,
                total_amount,
                favorite_product
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                name,
                phone,
                birthday,
                bool(vip),
                member_level,
                visitor.get("visitor_visit_count") or 0,
                line_user_id,
                registration_source,
                visitor.get("last_seen_at"),
                registration_face_filename,
                updated_by,
                total_amount or 0,
                favorite_product
            )
        )

        member_id = cursor.lastrowid

        # 3. 將既有散客人臉特徵複製到會員人臉表
        cursor.execute(
            """
            INSERT INTO face_images (
                member_id,
                image_path,
                encoding_data
            )
            SELECT
                %s,
                image_path,
                encoding_data
            FROM visitor_faces
            WHERE visitor_id = %s
            """,
            (member_id, visitor_id)
        )

        copied_face_count = cursor.rowcount

        # 4. 儲存本次註冊時上傳的人臉
        if normalized_registration_encoding is not None:
            cursor.execute(
                """
                INSERT INTO face_images (
                    member_id,
                    image_path,
                    encoding_data
                )
                VALUES (%s, %s, %s)
                """,
                (
                    member_id,
                    registration_image_path,
                    normalized_registration_encoding
                )
            )

        # 5. 標記 visitor 已轉會員
        cursor.execute(
            """
            UPDATE visitors
            SET
                converted_member_id = %s,
                updated_at = NOW()
            WHERE visitor_id = %s
              AND converted_member_id IS NULL
            """,
            (member_id, visitor_id)
        )

        if cursor.rowcount != 1:
            raise ValueError("visitor 轉會員失敗或已被其他流程轉換")

        # 6. 先結束已超過離店逾時、但尚未由攝影機執行緒關閉的紀錄。
        # 這可避免顧客實際離店後才註冊，舊散客歷史卻被改成會員。
        active_visit_timeout_seconds = max(
            1,
            int(active_visit_timeout_seconds or 60)
        )
        cursor.execute(
            """
            SELECT
                log_id,
                visit_time,
                recognized_at,
                last_seen_at
            FROM recognition_logs
            WHERE visitor_id = %s
              AND leave_time IS NULL
              AND visit_status IN ('arrived', 'staying')
              AND COALESCE(last_seen_at, visit_time, recognized_at)
                  < DATE_SUB(NOW(), INTERVAL %s SECOND)
            ORDER BY
                COALESCE(visit_time, recognized_at) DESC,
                log_id DESC
            LIMIT 1
            FOR UPDATE
            """,
            (visitor_id, active_visit_timeout_seconds)
        )
        stale_log = cursor.fetchone()
        closed_stale_log_id = None

        if stale_log:
            last_seen_value = (
                stale_log.get("last_seen_at")
                or stale_log.get("visit_time")
                or stale_log.get("recognized_at")
                or datetime.now()
            )
            visit_start_value = (
                stale_log.get("visit_time")
                or stale_log.get("recognized_at")
                or last_seen_value
            )

            if isinstance(last_seen_value, str):
                last_seen_value = datetime.strptime(
                    last_seen_value,
                    "%Y-%m-%d %H:%M:%S"
                )
            if isinstance(visit_start_value, str):
                visit_start_value = datetime.strptime(
                    visit_start_value,
                    "%Y-%m-%d %H:%M:%S"
                )

            stale_leave_time = (
                last_seen_value
                + timedelta(seconds=active_visit_timeout_seconds)
            )
            stale_stay_seconds = max(
                int((stale_leave_time - visit_start_value).total_seconds()),
                0
            )
            closed_stale_log_id = stale_log.get("log_id")

            cursor.execute(
                """
                UPDATE recognition_logs
                SET
                    recognition_status = 'recognized',
                    visit_status = 'left',
                    leave_time = %s,
                    stay_seconds = %s
                WHERE log_id = %s
                  AND leave_time IS NULL
                  AND visit_status IN ('arrived', 'staying')
                """,
                (
                    stale_leave_time,
                    stale_stay_seconds,
                    closed_stale_log_id
                )
            )

            if cursor.rowcount != 1:
                raise RuntimeError("逾時散客紀錄關閉失敗")

            cursor.execute(
                """
                UPDATE visitors
                SET
                    visitor_visit_count =
                        COALESCE(visitor_visit_count, 0) + 1,
                    last_seen_at = %s,
                    updated_at = NOW()
                WHERE visitor_id = %s
                """,
                (last_seen_value, visitor_id)
            )

        # 只有仍在離店逾時範圍內的紀錄，才原地切換成會員。
        cursor.execute(
            """
            SELECT log_id
            FROM recognition_logs
            WHERE visitor_id = %s
              AND leave_time IS NULL
              AND visit_status IN ('arrived', 'staying')
            ORDER BY
                COALESCE(visit_time, recognized_at) DESC,
                log_id DESC
            LIMIT 1
            FOR UPDATE
            """,
            (visitor_id,)
        )
        active_log = cursor.fetchone()
        converted_active_log_id = (
            active_log.get("log_id") if active_log else None
        )

        if converted_active_log_id is not None:
            cursor.execute(
                """
                UPDATE recognition_logs
                SET
                    subject_type = 'member',
                    member_id = %s,
                    name = %s,
                    vip = %s,
                    line_user_id = %s,
                    member_level = %s,
                    recognition_status = 'recognized'
                WHERE log_id = %s
                  AND leave_time IS NULL
                  AND visit_status IN ('arrived', 'staying')
                """,
                (
                    member_id,
                    name,
                    bool(vip),
                    line_user_id,
                    member_level,
                    converted_active_log_id
                )
            )

            if cursor.rowcount != 1:
                raise RuntimeError("尚未離店的散客紀錄轉換失敗")

        conn.commit()

        return {
            "success": True,
            "converted": True,
            "member_id": member_id,
            "visitor_id": visitor_id,
            "visitor_code": visitor.get("visitor_code"),
            "copied_face_count": copied_face_count,
            "converted_active_log_id": converted_active_log_id,
            "closed_stale_log_id": closed_stale_log_id
        }

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



def get_all_member_faces():
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            fi.face_id,
            fi.member_id,
            fi.image_path,
            fi.encoding_data,
            fi.created_at AS face_created_at,
            m.name,
            m.phone,
            m.birthday,
            m.vip,
            m.member_level,
            m.total_visit_count,
            m.last_visit_time,
            m.total_visit_time,
            m.updated_by,
            m.line_user_id,
            m.total_amount,
            m.favorite_product,
            m.face_image,
            m.registration_source,
            m.created_at AS member_created_at,
            m.updated_at AS member_updated_at
        FROM face_images fi
        JOIN members m
            ON fi.member_id = m.member_id
        WHERE fi.encoding_data IS NOT NULL
          AND fi.encoding_data <> ''
        ORDER BY fi.face_id ASC
        """

        cursor.execute(sql)
        rows = cursor.fetchall()

        valid_rows = []

        for row in rows:
            try:
                encoding = json.loads(row["encoding_data"])

                if not isinstance(encoding, list):
                    continue

                if len(encoding) != 128:
                    continue

                row["encoding_data"] = encoding

                row["member_level_text"] = get_member_level_text(
                    row.get("member_level")
                )

                valid_rows.append(row)

            except (TypeError, json.JSONDecodeError):
                print(
                    f"face_id={row['face_id']} 的 encoding_data 格式錯誤"
                )

        return valid_rows

    except Exception as e:
        print("取得會員人臉資料失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

def insert_visitor(
    visitor_code,
    display_name="Visitor",
    first_seen_at=None,
    last_seen_at=None
):
    conn = None
    cursor = None

    try:
        if not visitor_code:
            raise ValueError("visitor_code 不可為空")

        if first_seen_at is None:
            first_seen_at = datetime.now()

        if last_seen_at is None:
            last_seen_at = first_seen_at

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO visitors (
            visitor_code,
            display_name,
            first_seen_at,
            last_seen_at
        )
        VALUES (%s, %s, %s, %s)
        """

        cursor.execute(
            sql,
            (
                visitor_code,
                display_name,
                first_seen_at,
                last_seen_at
            )
        )

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增 visitor 失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_visitor_by_id(visitor_id):
    conn = None
    cursor = None

    try:
        if visitor_id is None:
            return None

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            visitor_id,
            visitor_code,
            display_name,
            visitor_visit_count,
            first_seen_at,
            last_seen_at,
            converted_member_id,
            best_face_image,
            created_at,
            updated_at
        FROM visitors
        WHERE visitor_id = %s
        """

        cursor.execute(sql, (visitor_id,))
        return cursor.fetchone()

    except Exception as e:
        print("查詢 visitor 失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def insert_visitor_face(
    visitor_id,
    image_path,
    encoding_data
):
    conn = None
    cursor = None

    try:
        if visitor_id is None:
            raise ValueError("visitor_id 不可為空")

        encoding_data = normalize_encoding_data(
            encoding_data
        )

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO visitor_faces (
            visitor_id,
            image_path,
            encoding_data
        )
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            sql,
            (
                visitor_id,
                image_path,
                encoding_data
            )
        )

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增 visitor 人臉資料失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def register_visitor_with_face(
    visitor_code,
    image_path,
    encoding_data,
    display_name=None,
    first_seen_at=None,
    last_seen_at=None
):
    """
    同一個資料庫 transaction 內建立固定散客與人臉資料。

    流程：
    1. 新增 visitors
    2. 取得 visitor_id
    3. 新增 visitor_faces
    4. 兩者都成功才 commit
    5. 任一步失敗就 rollback

    回傳：
    {
        "success": True,
        "visitor_id": int,
        "visitor_face_id": int,
        "visitor_code": str
    }
    """

    conn = None
    cursor = None

    try:
        if not visitor_code:
            raise ValueError("visitor_code 不可為空")

        if not image_path:
            raise ValueError("image_path 不可為空")

        if encoding_data is None:
            raise ValueError("encoding_data 不可為空")

        # NumPy array 轉成 Python list
        if hasattr(encoding_data, "tolist"):
            encoding_data = encoding_data.tolist()

        if not isinstance(encoding_data, (list, tuple)):
            raise ValueError(
                "encoding_data 必須是 list、tuple 或 NumPy array"
            )

        if len(encoding_data) != 128:
            raise ValueError(
                f"encoding_data 必須是 128 維，"
                f"目前為 {len(encoding_data)} 維"
            )

        encoding_json = json.dumps(
            list(encoding_data),
            ensure_ascii=False
        )

        current_time = datetime.now()

        if first_seen_at is None:
            first_seen_at = current_time

        if last_seen_at is None:
            last_seen_at = first_seen_at

        if not display_name:
            display_name = visitor_code

        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor()

        # 第一步：建立 visitors 固定身分
        visitor_sql = """
        INSERT INTO visitors (
            visitor_code,
            display_name,
            visitor_visit_count,
            first_seen_at,
            last_seen_at,
            best_face_image
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            visitor_sql,
            (
                visitor_code,
                display_name,
                0,
                first_seen_at,
                last_seen_at,
                image_path
            )
        )

        visitor_id = cursor.lastrowid

        if visitor_id is None:
            raise RuntimeError("建立 visitor 後未取得 visitor_id")

        # 第二步：寫入該散客的 128 維人臉 encoding
        face_sql = """
        INSERT INTO visitor_faces (
            visitor_id,
            image_path,
            encoding_data
        )
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            face_sql,
            (
                visitor_id,
                image_path,
                encoding_json
            )
        )

        visitor_face_id = cursor.lastrowid

        if visitor_face_id is None:
            raise RuntimeError(
                "建立 visitor_faces 後未取得 visitor_face_id"
            )

        # visitors 與 visitor_faces 都成功才提交
        conn.commit()

        print("========== Visitor Registered ==========")
        print(f"visitor_id: {visitor_id}")
        print(f"visitor_code: {visitor_code}")
        print(f"visitor_face_id: {visitor_face_id}")
        print(f"image_path: {image_path}")
        print("========================================")

        return {
            "success": True,
            "visitor_id": visitor_id,
            "visitor_face_id": visitor_face_id,
            "visitor_code": visitor_code
        }

    except Exception as e:
        if conn:
            conn.rollback()

        print("========== Visitor Registration Failed ==========")
        print(f"visitor_code: {visitor_code}")
        print(f"error: {e}")
        print("已 rollback，未保留不完整的散客資料")
        print("=================================================")

        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def get_all_visitor_faces():
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            vf.visitor_face_id,
            vf.visitor_id,
            vf.image_path,
            vf.encoding_data,
            vf.created_at AS face_created_at,
            v.visitor_code,
            v.display_name,
            v.visitor_visit_count,
            v.first_seen_at,
            v.last_seen_at,
            v.converted_member_id,
            v.best_face_image,
            v.created_at AS visitor_created_at,
            v.updated_at AS visitor_updated_at
        FROM visitor_faces vf
        JOIN visitors v
            ON vf.visitor_id = v.visitor_id
        WHERE vf.encoding_data IS NOT NULL
        AND vf.encoding_data <> ''
        AND v.converted_member_id IS NULL
        ORDER BY vf.visitor_face_id ASC
                """

        cursor.execute(sql)
        rows = cursor.fetchall()

        valid_rows = []

        for row in rows:
            try:
                encoding = json.loads(
                    row["encoding_data"]
                )

                if not isinstance(encoding, list):
                    continue

                if len(encoding) != 128:
                    continue

                row["encoding_data"] = encoding
                row["subject_type"] = "visitor"
                row["member_id"] = None

                valid_rows.append(row)

            except (TypeError, json.JSONDecodeError):
                print(
                    f"visitor_face_id="
                    f"{row['visitor_face_id']} "
                    f"的 encoding_data 格式錯誤"
                )

        return valid_rows

    except Exception as e:
        print("取得 visitor 人臉資料失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def get_dashboard_summary():
    """
    查詢第四週 Dashboard 統計資料。

    定義：
    - today_visitors：同一位正式會員或固定散客一天只算一次。
    - today_visit_count：今天每一筆成功建立的會員或固定散客到店紀錄都算一次。
    - today_vip：今天成功辨識到的 VIP 會員（不重複）。
    - today_visitors_fixed：今天成功辨識到的固定散客（不重複）。
    - current_people：所有尚未離店的人數，不侷限當日。
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            (
                SELECT COUNT(*)
                FROM recognition_logs
                WHERE DATE(visit_time) = CURDATE()
                  AND subject_type IN ('member', 'visitor')
                  AND recognition_status = 'recognized'
            ) AS today_visit_count,
            (
                SELECT COUNT(DISTINCT CONCAT(subject_type, ':',
                       CASE WHEN subject_type = 'member' THEN member_id ELSE visitor_id END))
                FROM recognition_logs
                WHERE DATE(visit_time) = CURDATE()
                  AND subject_type IN ('member', 'visitor')
                  AND recognition_status = 'recognized'
            ) AS today_visitors,
            (
                SELECT COUNT(DISTINCT rl.member_id)
                FROM recognition_logs AS rl
                JOIN members AS m
                  ON m.member_id = rl.member_id
                WHERE DATE(rl.visit_time) = CURDATE()
                  AND rl.subject_type = 'member'
                  AND rl.recognition_status = 'recognized'
                  AND (
                      m.vip = TRUE
                      OR m.member_level = 'vip'
                  )
            ) AS today_vip,
            (
                SELECT COUNT(DISTINCT visitor_id)
                FROM recognition_logs
                WHERE DATE(visit_time) = CURDATE()
                  AND subject_type = 'visitor'
                  AND recognition_status = 'recognized'
            ) AS today_visitors_fixed,
            (
                SELECT COUNT(DISTINCT CONCAT(subject_type, ':',
                       CASE WHEN subject_type = 'member' THEN member_id ELSE visitor_id END))
                FROM recognition_logs
                WHERE subject_type IN ('member', 'visitor')
                  AND leave_time IS NULL
                  AND visit_status IN ('arrived', 'staying')
            ) AS current_people,
            (
                SELECT COUNT(*)
                FROM members
                WHERE DATE(created_at) = CURDATE()
            ) AS today_new_members,
            (
            SELECT COALESCE(
                ROUND(AVG(stay_seconds) / 60, 1),
                0
            )
            FROM recognition_logs
            WHERE DATE(visit_time) = CURDATE()
            AND leave_time IS NOT NULL
            AND stay_seconds IS NOT NULL
            AND stay_seconds > 0
            ) AS average_stay_minutes
            """

        cursor.execute(sql)
        summary = cursor.fetchone()

        summary = summary or {}
        for key in (
            "today_visit_count",
            "today_visitors",
            "today_vip",
            "today_visitors_fixed",
            "current_people",
            "today_new_members",
        ):
            summary[key] = int(summary.get(key) or 0)

        summary["average_stay_minutes"] = float(
            summary.get("average_stay_minutes") or 0
        )

        # 保留現有 dashboard.html 的舊欄位，避免前端未同步時白畫面。
        summary["today_visits"] = summary["today_visit_count"]
        summary["new_members"] = summary["today_new_members"]
        summary["current_in_store"] = summary["current_people"]
        return summary

    except Exception as e:
        print("取得 Dashboard 統計失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_recent_members(limit=10):
    """回傳 Dashboard 新會員列表所需的標準欄位。"""
    limit = max(1, min(int(limit), 100))
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT member_id, name, phone, registration_source,
                   member_level, created_at
            FROM members
            ORDER BY created_at DESC, member_id DESC
            LIMIT %s
            """,
            (limit,)
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

def get_recent_recognitions(limit=10):
    """
    取得最近的辨識紀錄。

    limit：
    決定最多回傳幾筆資料，預設為 10 筆。
    """

    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 10

        if limit > 100:
            limit = 100

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            rl.log_id,
            rl.subject_type,
            rl.member_id,
            rl.visitor_id,
            rl.visitor_code,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.name, rl.name)
                ELSE rl.name
            END AS name,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.vip, rl.vip)
                ELSE rl.vip
            END AS vip,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.member_level, rl.member_level)
                ELSE rl.member_level
            END AS member_level,
            rl.confidence,
            rl.recognition_status,
            rl.visit_status,
            rl.camera_id,
            rl.camera_location,
            rl.visit_time,
            rl.recognized_at,
            rl.last_seen_at,
            rl.leave_time,
            rl.stay_seconds,
            ROUND(rl.stay_seconds / 60.0, 2) AS stay_minutes,
            rl.created_at
        FROM recognition_logs AS rl
        LEFT JOIN members AS m
          ON m.member_id = rl.member_id
         AND rl.subject_type = 'member'
        ORDER BY rl.recognized_at DESC, rl.log_id DESC
        LIMIT %s
        """

        cursor.execute(sql, (limit,))
        rows = cursor.fetchall()

        for row in rows:
            row["member_level_text"] = get_member_level_text(
                row.get("member_level")
            )

        return rows

    except (TypeError, ValueError):
        print("取得最近辨識紀錄失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得最近辨識紀錄失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def get_recent_vip_notifications(limit=10):
    """
    取得最近的 VIP 通知紀錄。

    limit：
    決定最多回傳幾筆資料，預設為 10 筆。
    """

    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 10

        if limit > 100:
            limit = 100

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            vn.notification_id,
            vn.member_id,
            vn.log_id,
            vn.line_user_id,
            vn.message,
            vn.status,
            vn.sent_at,
            vn.created_at,
            m.name AS member_name,
            m.vip,
            m.member_level,
            rl.confidence,
            rl.camera_id,
            rl.camera_location,
            rl.recognized_at
        FROM vip_notifications vn
        LEFT JOIN members m
            ON vn.member_id = m.member_id
        LEFT JOIN recognition_logs rl
            ON vn.log_id = rl.log_id
        ORDER BY vn.created_at DESC,
                 vn.notification_id DESC
        LIMIT %s
        """

        cursor.execute(sql, (limit,))
        rows = cursor.fetchall()

        for row in rows:
            row["member_level_text"] = get_member_level_text(
                row.get("member_level")
            )

        return rows

    except (TypeError, ValueError):
        print("取得最近 VIP 通知失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得最近 VIP 通知失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_active_lottery_prizes():
    """
    取得目前可以抽到的獎品。
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            prize_id,
            prize_code,
            prize_name,
            prize_type,
            prize_value,
            probability_weight,
            stock_quantity,
            prize_status
        FROM lottery_prizes
        WHERE prize_status = 'active'
          AND (
                stock_quantity IS NULL
                OR stock_quantity > 0
              )
        ORDER BY prize_id ASC
        """

        cursor.execute(sql)
        return cursor.fetchall()

    except Exception as e:
        print("取得抽獎獎品失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def has_member_completed_lottery(member_id):
    """
    檢查會員是否已抽到最終獎項。
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            lottery_id,
            member_id,
            prize_id,
            prize_name,
            result,
            is_final,
            redeemed,
            redeemed_at,
            created_at
        FROM lottery_records
        WHERE member_id = %s
          AND is_final = TRUE
        ORDER BY created_at DESC, lottery_id DESC
        LIMIT 1
        """

        cursor.execute(sql, (member_id,))
        return cursor.fetchone()

    except Exception as e:
        print("檢查會員抽獎資格失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()            


def insert_lottery_record(
    member_id,
    prize_id,
    prize_name,
    result=None,
    coupon_id=None,
    is_final=True,
    can_retry=False
):
    """
    儲存會員抽獎結果。
    """

    conn = None
    cursor = None

    try:
        if member_id is None:
            raise ValueError("member_id 不可為空")

        if prize_id is None:
            raise ValueError("prize_id 不可為空")

        if not prize_name:
            raise ValueError("prize_name 不可為空")

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO lottery_records (
            member_id,
            prize_id,
            coupon_id,
            prize_name,
            result,
            is_final,
            can_retry,
            redeemed,
            redeemed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL)
        """

        cursor.execute(
            sql,
            (
                member_id,
                prize_id,
                coupon_id,
                prize_name,
                result,
                to_bool(is_final),
                to_bool(can_retry)
            )
        )

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增抽獎紀錄失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_member_lottery_records(member_id):
    """
    查詢會員的所有抽獎紀錄。
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            lr.lottery_id,
            lr.member_id,
            lr.prize_id,
            lr.coupon_id,
            lr.prize_name,
            lr.result,
            lr.is_final,
            lr.can_retry,
            lr.redeemed,
            lr.redeemed_at,
            lr.created_at,
            lp.prize_code,
            lp.prize_type,
            lp.prize_value
        FROM lottery_records lr
        JOIN lottery_prizes lp
            ON lr.prize_id = lp.prize_id
        WHERE lr.member_id = %s
        ORDER BY lr.created_at DESC,
                 lr.lottery_id DESC
        """

        cursor.execute(sql, (member_id,))
        return cursor.fetchall()

    except Exception as e:
        print("取得會員抽獎紀錄失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_member_prize(member_id):
    """
    查詢會員在目前活動（LOTTERY_CAMPAIGN_CODE）抽中的最終獎項與兌換資訊。
    跟 draw_lottery_for_member() 裡「已抽過」那段查的是同一張 member_prizes，
    這裡抽成獨立函式給 GET /api/lottery/result/<member_id> 用，沒有實際查詢邏輯的改動。
    沒抽過的話回傳 None。
    """
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                mp.member_prize_id,
                mp.member_id,
                mp.prize_id,
                mp.campaign_code,
                mp.prize_code,
                mp.redeem_token,
                mp.status,
                mp.issued_at,
                mp.expires_at,
                mp.redeemed_at,
                mp.redeemed_by,
                lp.prize_name,
                lp.prize_type,
                lp.prize_value
            FROM member_prizes mp
            JOIN lottery_prizes lp
                ON mp.prize_id = lp.prize_id
            WHERE mp.member_id = %s
              AND mp.campaign_code = %s
            LIMIT 1
            """,
            (member_id, LOTTERY_CAMPAIGN_CODE)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def draw_lottery_for_member(member_id):
    """
    會員正式抽獎。

    這個函式會在同一個 transaction 中完成：
    1. 鎖定會員資料
    2. 檢查是否已經抽到最終獎項
    3. 查詢目前可抽的獎品
    4. 依照 probability_weight 抽獎
    5. 扣除有限庫存
    6. 寫入 lottery_records
    7. commit
    """

    conn = None
    cursor = None

    try:
        if member_id is None:
            raise ValueError("member_id 不可為空")

        member_id = int(member_id)

        conn = get_connection()

        # 明確關閉自動提交，
        # 讓下面所有 SQL 都在同一個 transaction 裡
        conn.autocommit = False

        cursor = conn.cursor(dictionary=True)

        # -------------------------------------------------
        # 第 1 步：鎖定這一位會員
        # -------------------------------------------------
        # FOR UPDATE 的意思：
        # 如果同一位會員快速按兩次，
        # 第二個請求必須等待第一個請求結束。
        cursor.execute(
            """
            SELECT
                member_id,
                name
            FROM members
            WHERE member_id = %s
            FOR UPDATE
            """,
            (member_id,)
        )

        member = cursor.fetchone()

        if member is None:
            raise ValueError("找不到這位會員")

        # -------------------------------------------------
        # 第 2 步：檢查是否已有最終獎項
        # -------------------------------------------------
        cursor.execute(
            """
            SELECT
                mp.member_prize_id,
                mp.member_id,
                mp.prize_id,
                mp.campaign_code,
                mp.prize_code,
                mp.redeem_token,
                mp.status,
                mp.issued_at,
                mp.expires_at,
                mp.redeemed_at,
                mp.redeemed_by,
                lp.prize_name,
                lp.prize_type,
                lp.prize_value
            FROM member_prizes mp
            JOIN lottery_prizes lp
                ON mp.prize_id = lp.prize_id
            WHERE mp.member_id = %s
              AND mp.campaign_code = %s
            LIMIT 1
            """,
            (
                member_id,
                LOTTERY_CAMPAIGN_CODE
            )
        )

        completed_record = cursor.fetchone()

        if completed_record is not None:
            conn.rollback()
            completed_prize_name = get_lottery_prize_display_name(
                completed_record["prize_code"],
                completed_record["prize_name"],
            )

            qr_value = (
                f"{REDEMPTION_BASE_URL}/redeem/"
                f"{completed_record['redeem_token']}"
            )

            return {
                "success": True,
                "message": "這位會員已經完成抽獎",
                "already_completed": True,
                "is_final": True,
                "can_retry": False,
                "prize": {
                    "prize_id": completed_record["prize_id"],
                    "prize_code": completed_record["prize_code"],
                    "prize_name": completed_prize_name,
                    "prize_type": completed_record["prize_type"],
                    "prize_value": completed_record["prize_value"]
                },
                "redemption": {
                    "member_prize_id": completed_record[
                        "member_prize_id"
                    ],
                    "token": completed_record["redeem_token"],
                    "qr_value": qr_value,
                    "status": completed_record["status"],
                    "expires_at": completed_record["expires_at"]
                }
            }
        # -------------------------------------------------
        # 第 3 步：查詢目前可以抽的獎品
        # -------------------------------------------------
        cursor.execute(
            """
            SELECT
                prize_id,
                prize_code,
                prize_name,
                prize_type,
                prize_value,
                probability_weight,
                stock_quantity,
                prize_status,
                coupon_id
            FROM lottery_prizes
            WHERE prize_status = 'active'
              AND probability_weight > 0
              AND (
                    stock_quantity IS NULL
                    OR stock_quantity > 0
                  )
            ORDER BY prize_id ASC
            FOR UPDATE
            """
        )

        prizes = cursor.fetchall()

        if not prizes:
            raise ValueError("目前沒有可以抽的獎品")

        # -------------------------------------------------
        # 第 4 步：依照權重抽獎
        # -------------------------------------------------
        weights = [
            prize["probability_weight"]
            for prize in prizes
        ]

        selected_prize = random.choices(
            prizes,
            weights=weights,
            k=1
        )[0]
        selected_prize = dict(selected_prize)
        selected_prize["prize_name"] = (
            get_lottery_prize_display_name(
                selected_prize.get("prize_code"),
                selected_prize.get("prize_name"),
            )
        )

        prize_id = selected_prize["prize_id"]
        prize_name = selected_prize["prize_name"]
        prize_type = selected_prize["prize_type"]
        coupon_id = selected_prize.get("coupon_id")

        # 「再抽一次」不是最終獎品
        is_final = prize_type != "retry"

        # -------------------------------------------------
        # 第 5 步：有限庫存的獎品要扣 1
        # -------------------------------------------------
        if selected_prize["stock_quantity"] is not None:
            cursor.execute(
                """
                UPDATE lottery_prizes
                SET stock_quantity = stock_quantity - 1
                WHERE prize_id = %s
                  AND stock_quantity > 0
                """,
                (prize_id,)
            )

            if cursor.rowcount != 1:
                raise RuntimeError("獎品庫存不足，請重新抽獎")

        # -------------------------------------------------
        # 第 6 步：寫入抽獎紀錄
        # -------------------------------------------------
        cursor.execute(
            """
            INSERT INTO lottery_records (
                member_id,
                prize_id,
                coupon_id,
                lottery_name,
                prize,
                draw_time,
                status,
                prize_name,
                result,
                is_final,
                can_retry,
                redeemed,
                redeemed_at
            )
             VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW(),
                %s,
                %s,
                %s,
                %s,
                %s,
                FALSE,
                NULL
            )
            """,
            (
                member_id,
                prize_id,
                coupon_id,
                "新會員抽獎",
                prize_name,
                "中獎" if is_final else "未完成",
                prize_name,
                prize_name,
                to_bool(is_final),
                to_bool(not is_final)
            )
        )

        lottery_id = cursor.lastrowid

        redemption = None
        member_coupon_id = None

# 如果抽中的獎項有設定 coupon_id，
# 就把優惠券正式發給這位會員。
        if coupon_id is not None:
            cursor.execute(
                """
                INSERT INTO member_coupons (
                    member_id,
                    coupon_id,
                    source,
                    status,
                    receive_time,
                    used_time
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'unused',
                    NOW(),
                    NULL
                )
                """,
                (
                    member_id,
                    coupon_id,
                    LOTTERY_CAMPAIGN_CODE
                )
            )

            member_coupon_id = cursor.lastrowid


        # 只有最終獎才建立 member_prizes，下一次抽獎才會被視為已完成。
        # retry 獎不建立這筆資料，因此前端可安全地再抽一次。
        if is_final:
            redeem_token = secrets.token_urlsafe(24)

            expires_at = (
                datetime.now()
                + timedelta(
                    days=LOTTERY_REDEMPTION_DAYS
                )
            )

            cursor.execute(
                """
                INSERT INTO member_prizes (
                    member_id,
                    prize_id,
                    campaign_code,
                    prize_code,
                    redeem_token,
                    status,
                    expires_at
                )
                VALUES (%s, %s, %s, %s, %s, 'unused', %s)
                """,
                (
                    member_id,
                    prize_id,
                    LOTTERY_CAMPAIGN_CODE,
                    selected_prize["prize_code"],
                    redeem_token,
                    expires_at
                )
            )
            redemption = {
                "token": redeem_token,
                "qr_value": (
                    f"{REDEMPTION_BASE_URL}/redeem/"
                    f"{redeem_token}"
                ),
                "status": "unused",
                "expires_at": expires_at
            }

        conn.commit()
        
        # -------------------------------------------------
        # 第 7 步：全部成功後才 commit
        # -------------------------------------------------

        return {
            "success": True,
            "message": "抽獎成功",
            "already_completed": False,
            "lottery_id": lottery_id,
            
            "member_coupon_id": member_coupon_id,
            "coupon_id": coupon_id,
            "coupon_issued": member_coupon_id is not None,
            "is_final": to_bool(is_final),
            "can_retry": to_bool(not is_final),
            "redemption": redemption,
            "prize": selected_prize
        }

    except Exception as e:
        if conn:
            conn.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def get_redemption_by_token(redeem_token):
    """
    根據 QR token 查詢會員中獎與兌換資料。
    """

    conn = None
    cursor = None

    try:
        if not redeem_token:
            return None

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            mp.member_prize_id,
            mp.member_id,
            mp.prize_id,
            mp.campaign_code,
            mp.prize_code,
            mp.redeem_token,
            mp.status,
            mp.issued_at,
            mp.expires_at,
            mp.redeemed_at,
            mp.redeemed_by,

            m.name AS member_name,
            m.phone AS member_phone,

            lp.prize_name,
            lp.prize_type,
            lp.prize_value
        FROM member_prizes mp
        JOIN members m
            ON mp.member_id = m.member_id
        JOIN lottery_prizes lp
            ON mp.prize_id = lp.prize_id
        WHERE mp.redeem_token = %s
        LIMIT 1
        """

        cursor.execute(sql, (redeem_token,))
        return cursor.fetchone()

    except Exception as e:
        print("查詢兌換資料失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

def redeem_member_prize(redeem_token, redeemed_by):
    """
    核銷會員獎品。

    核銷成功時：
    1. member_prizes.status 改成 redeemed
    2. 如果有對應 member_coupon_id，
       member_coupons.status 一起改成 used
    """

    conn = None
    cursor = None

    try:
        if not redeem_token:
            raise ValueError("redeem_token 不可為空")

        if not redeemed_by:
            raise ValueError("redeemed_by 不可為空")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 先鎖定資料，避免同一張 QR Code 同時被核銷兩次
        cursor.execute(
            """
            SELECT
                member_prize_id,
                member_id,
                prize_id,
                status,
                expires_at,
                (
                    SELECT mc.member_coupon_id
                    FROM member_coupons AS mc
                    JOIN lottery_prizes AS lp
                        ON lp.coupon_id = mc.coupon_id
                    WHERE mc.member_id = member_prizes.member_id
                      AND lp.prize_id = member_prizes.prize_id
                      AND mc.source = %s
                    ORDER BY mc.member_coupon_id DESC
                    LIMIT 1
                ) AS member_coupon_id
            FROM member_prizes
            WHERE redeem_token = %s
            FOR UPDATE
            """,
            (
                LOTTERY_CAMPAIGN_CODE,
                redeem_token,
            )
        )

        prize_record = cursor.fetchone()

        if prize_record is None:
            conn.rollback()

            return {
                "success": False,
                "message": "找不到這張兌換 QR Code"
            }

        if prize_record["status"] == "redeemed":
            conn.rollback()

            return {
                "success": False,
                "message": "此獎品已經兌換過"
            }

        if prize_record["status"] == "expired":
            conn.rollback()

            return {
                "success": False,
                "message": "此獎品已過期"
            }

        expires_at = prize_record["expires_at"]

        if (
            expires_at is not None
            and expires_at <= datetime.now()
        ):
            conn.rollback()

            return {
                "success": False,
                "message": "此獎品已過期"
            }

        if prize_record["status"] != "unused":
            conn.rollback()

            return {
                "success": False,
                "message": "此獎品目前無法核銷"
            }

        # 更新 member_prizes
        cursor.execute(
            """
            UPDATE member_prizes
            SET
                status = 'redeemed',
                redeemed_at = CURRENT_TIMESTAMP,
                redeemed_by = %s
            WHERE member_prize_id = %s
              AND status = 'unused'
            """,
            (
                redeemed_by,
                prize_record["member_prize_id"]
            )
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "更新 member_prizes 核銷狀態失敗"
            )

        member_coupon_id = prize_record["member_coupon_id"]

        # 有優惠券才同步更新 member_coupons
        if member_coupon_id is not None:
            cursor.execute(
                """
                UPDATE member_coupons
                SET
                    status = 'used',
                    used_time = CURRENT_TIMESTAMP
                WHERE member_coupon_id = %s
                  AND status = 'unused'
                """,
                (member_coupon_id,)
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "更新 member_coupons 使用狀態失敗"
                )

        # 兩張表都成功才提交
        conn.commit()

        return {
            "success": True,
            "message": "獎品核銷成功"
        }

    except Exception as e:
        if conn is not None:
            conn.rollback()

        print("核銷獎品失敗：", e)
        raise

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None and conn.is_connected():
            conn.close()



def get_all_visitors(limit=100):
    """
    取得散客列表。
    """
    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 100

        if limit > 500:
            limit = 500

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            visitor_id,
            visitor_code,
            display_name,
            visitor_visit_count,
            first_seen_at,
            last_seen_at,
            converted_member_id,
            best_face_image,
            created_at,
            updated_at
        FROM visitors
        ORDER BY last_seen_at DESC,
                 visitor_id DESC
        LIMIT %s
        """

        cursor.execute(sql, (limit,))
        return cursor.fetchall()

    except (TypeError, ValueError):
        print("取得散客列表失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得散客列表失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close() 

def get_recognition_logs(
    limit=100,
    subject_type=None,
    visit_status=None,
    member_id=None,
    visitor_id=None,
    start_date=None,
    end_date=None
):
    """
    查詢辨識紀錄，提供 Recognition Logs 頁面使用。
    """
    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 100

        if limit > 500:
            limit = 500

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            rl.log_id,
            rl.subject_type,
            rl.member_id,
            rl.visitor_id,
            rl.visitor_code,
            rl.camera_id,
            rl.camera_location,
            (
                SELECT source_visitor.visitor_id
                FROM visitors AS source_visitor
                WHERE source_visitor.converted_member_id =
                    rl.member_id
                ORDER BY source_visitor.visitor_id ASC
                LIMIT 1
            ) AS source_visitor_id,
            (
                SELECT source_visitor.visitor_code
                FROM visitors AS source_visitor
                WHERE source_visitor.converted_member_id =
                    rl.member_id
                ORDER BY source_visitor.visitor_id ASC
                LIMIT 1
            ) AS source_visitor_code,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.name, rl.name)
                ELSE rl.name
            END AS name,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.vip, rl.vip)
                ELSE rl.vip
            END AS vip,
            rl.line_user_id,
            rl.confidence,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.member_level, rl.member_level)
                ELSE rl.member_level
            END AS member_level,
            rl.recognition_status,
            rl.visit_status,
            rl.visit_time,
            rl.recognized_at,
            rl.last_seen_at,
            rl.leave_time,
            rl.stay_seconds,
            ROUND(rl.stay_seconds / 60.0, 2) AS stay_minutes,
            rl.created_at
        FROM recognition_logs AS rl
        LEFT JOIN members AS m
          ON m.member_id = rl.member_id
         AND rl.subject_type = 'member'
        WHERE 1 = 1
        """

        params = []

        if subject_type:
            sql += " AND rl.subject_type = %s"
            params.append(subject_type)

        if visit_status:
            sql += " AND rl.visit_status = %s"
            params.append(visit_status)

        if member_id is not None:
            sql += " AND rl.member_id = %s"
            params.append(member_id)

        if visitor_id is not None:
            sql += " AND rl.visitor_id = %s"
            params.append(visitor_id)

        if start_date:
            sql += " AND DATE(rl.visit_time) >= %s"
            params.append(start_date)

        if end_date:
            sql += " AND DATE(rl.visit_time) <= %s"
            params.append(end_date)

        sql += """
        ORDER BY rl.visit_time DESC, rl.log_id DESC
        LIMIT %s
        """
        params.append(limit)

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        for row in rows:
            row["member_level_text"] = get_member_level_text(
                row.get("member_level")
            )

        return rows

    except (TypeError, ValueError):
        print("取得辨識紀錄失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得辨識紀錄失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

# =========================================================
# 生日禮功能
# 放在 get_member_coupons() 前面，避免改動既有 API 與查詢格式。
# =========================================================
def _coerce_datetime(value=None):
    """
    將 None、date、datetime 或 ISO 日期字串統一轉成 datetime。

    這個 helper 讓正式執行可使用現在時間，測試時也能傳入
    "2026-08-06"，不用修改電腦日期。
    """
    if value is None:
        return datetime.now()

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, time.min)

    if isinstance(value, str):
        cleaned_value = value.strip()

        try:
            return datetime.fromisoformat(cleaned_value)
        except ValueError as error:
            raise ValueError(
                "as_of 日期格式必須是 YYYY-MM-DD "
                "或合法的 ISO datetime"
            ) from error

    raise TypeError(
        "as_of 必須是 None、date、datetime 或 ISO 日期字串"
    )


def _month_bounds(value=None):
    """回傳指定日期所在月份的開始與結束時間。"""
    current = _coerce_datetime(value)
    last_day = monthrange(current.year, current.month)[1]

    start_at = datetime(
        current.year,
        current.month,
        1,
        0,
        0,
        0,
    )

    end_at = datetime(
        current.year,
        current.month,
        last_day,
        23,
        59,
        59,
    )

    return start_at, end_at



def issue_registration_welcome_coupon(member_id):
    """
    發送新會員 100 元迎新禮。

    使用 member_coupons.source='registration_welcome'
    判斷是否已領取，確保同一會員只能領一次。
    """
    try:
        member_id = int(member_id)
    except (TypeError, ValueError) as error:
        raise ValueError("member_id 必須是整數") from error

    if member_id <= 0:
        raise ValueError("member_id 必須大於 0")

    conn = None
    cursor = None

    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT member_id
            FROM members
            WHERE member_id = %s
            FOR UPDATE
            """,
            (member_id,),
        )

        if cursor.fetchone() is None:
            raise ValueError("找不到要發送迎新禮的會員")

        cursor.execute(
            """
            SELECT member_coupon_id, coupon_id
            FROM member_coupons
            WHERE member_id = %s
              AND source = %s
            LIMIT 1
            """,
            (
                member_id,
                REGISTRATION_WELCOME_COUPON_SOURCE,
            ),
        )

        existing = cursor.fetchone()

        if existing is not None:
            conn.commit()
            return {
                "member_id": member_id,
                "member_coupon_id": existing[
                    "member_coupon_id"
                ],
                "coupon_id": existing["coupon_id"],
                "source": REGISTRATION_WELCOME_COUPON_SOURCE,
                "issued": False,
                "reason": "迎新禮已發送",
            }

        cursor.execute(
            """
            SELECT coupon_id
            FROM coupons
            WHERE coupon_name = %s
              AND status = 'active'
            LIMIT 1
            """,
            (REGISTRATION_WELCOME_COUPON_NAME,),
        )

        coupon = cursor.fetchone()

        if coupon is None:
            cursor.execute(
                """
                INSERT INTO coupons (
                    coupon_name,
                    description,
                    discount_type,
                    discount_value,
                    start_at,
                    end_at,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    'amount',
                    100,
                    NULL,
                    NULL,
                    'active'
                )
                """,
                (
                    REGISTRATION_WELCOME_COUPON_NAME,
                    "完成會員註冊後贈送，消費時可折抵 100 元",
                ),
            )
            coupon_id = cursor.lastrowid
        else:
            coupon_id = coupon["coupon_id"]

        cursor.execute(
            """
            INSERT INTO member_coupons (
                member_id,
                coupon_id,
                source,
                status,
                receive_time,
                used_time
            )
            VALUES (
                %s,
                %s,
                %s,
                'unused',
                NOW(),
                NULL
            )
            """,
            (
                member_id,
                coupon_id,
                REGISTRATION_WELCOME_COUPON_SOURCE,
            ),
        )

        member_coupon_id = cursor.lastrowid
        conn.commit()

        return {
            "member_id": member_id,
            "member_coupon_id": member_coupon_id,
            "coupon_id": coupon_id,
            "coupon_name": REGISTRATION_WELCOME_COUPON_NAME,
            "source": REGISTRATION_WELCOME_COUPON_SOURCE,
            "issued": True,
        }

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def issue_birthday_coupon(member_id, as_of=None):
    """
    在會員生日月份發送一次 200 元生日禮。

    規則：
    1. 會員必須存在且 birthday 有資料。
    2. 只有生日月份可以領取。
    3. source 使用 birthday_年份，同一會員每年只能領一次。
    4. 優惠券有效期為該生日月份第一天到最後一天。
    """
    try:
        member_id = int(member_id)
    except (TypeError, ValueError) as error:
        raise ValueError("member_id 必須是整數") from error

    if member_id <= 0:
        raise ValueError("member_id 必須大於 0")

    current = _coerce_datetime(as_of)
    start_at, end_at = _month_bounds(current)

    source = (
        f"{BIRTHDAY_COUPON_SOURCE_PREFIX}"
        f"{current.year}"
    )

    coupon_name = (
        f"{BIRTHDAY_COUPON_NAME}"
        f"（{current.year}-{current.month:02d}）"
    )

    conn = None
    cursor = None

    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        # 先鎖定會員，避免同一位會員同時重複領券。
        cursor.execute(
            """
            SELECT member_id, birthday
            FROM members
            WHERE member_id = %s
            FOR UPDATE
            """,
            (member_id,),
        )

        member = cursor.fetchone()

        if member is None:
            raise ValueError("找不到要發送生日禮的會員")

        birthday = member.get("birthday")

        if birthday is None:
            conn.commit()
            return {
                "member_id": member_id,
                "issued": False,
                "reason": "會員尚未填寫生日",
            }

        if isinstance(birthday, datetime):
            birthday = birthday.date()

        elif isinstance(birthday, str):
            try:
                birthday = date.fromisoformat(
                    birthday.strip()[:10]
                )
            except ValueError as error:
                raise ValueError(
                    "members.birthday 不是合法日期"
                ) from error

        if not isinstance(birthday, date):
            raise TypeError(
                "members.birthday 必須是 DATE 或日期字串"
            )

        if birthday.month != current.month:
            conn.commit()
            return {
                "member_id": member_id,
                "issued": False,
                "reason": "目前不是會員生日月份",
            }

        # source=birthday_2026 可防止同一會員同一年重複領取。
        cursor.execute(
            """
            SELECT member_coupon_id, coupon_id
            FROM member_coupons
            WHERE member_id = %s
              AND source = %s
            LIMIT 1
            """,
            (member_id, source),
        )

        existing = cursor.fetchone()

        if existing is not None:
            conn.commit()
            return {
                "member_id": member_id,
                "member_coupon_id": existing[
                    "member_coupon_id"
                ],
                "coupon_id": existing["coupon_id"],
                "source": source,
                "issued": False,
                "reason": "本年度生日禮已發送",
            }

        # 每個月份建立一張共用生日券，會員領券紀錄放在 member_coupons。
        cursor.execute(
            """
            SELECT coupon_id
            FROM coupons
            WHERE coupon_name = %s
              AND status = 'active'
            LIMIT 1
            """,
            (coupon_name,),
        )

        coupon = cursor.fetchone()

        if coupon is None:
            cursor.execute(
                """
                INSERT INTO coupons (
                    coupon_name,
                    description,
                    discount_type,
                    discount_value,
                    start_at,
                    end_at,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    'amount',
                    200,
                    %s,
                    %s,
                    'active'
                )
                """,
                (
                    coupon_name,
                    "生日月份專屬優惠，消費時可折抵 200 元",
                    start_at,
                    end_at,
                ),
            )
            coupon_id = cursor.lastrowid

        else:
            coupon_id = coupon["coupon_id"]

        cursor.execute(
            """
            INSERT INTO member_coupons (
                member_id,
                coupon_id,
                source,
                status,
                receive_time,
                used_time
            )
            VALUES (
                %s,
                %s,
                %s,
                'unused',
                NOW(),
                NULL
            )
            """,
            (member_id, coupon_id, source),
        )

        member_coupon_id = cursor.lastrowid
        conn.commit()

        return {
            "member_id": member_id,
            "member_coupon_id": member_coupon_id,
            "coupon_id": coupon_id,
            "coupon_name": coupon_name,
            "source": source,
            "start_at": start_at,
            "end_at": end_at,
            "issued": True,
        }

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def issue_monthly_birthday_coupons(as_of=None):
    """
    找出指定月份生日的所有會員，逐一發送生日禮。

    可由排程、後台管理功能或 LINE 組每天呼叫一次；
    issue_birthday_coupon() 會防止同一年重複發送。
    """
    current = _coerce_datetime(as_of)
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT member_id
            FROM members
            WHERE birthday IS NOT NULL
              AND MONTH(birthday) = %s
            ORDER BY member_id
            """,
            (current.month,),
        )
        members = cursor.fetchall()

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

    issued_count = 0
    existing_count = 0
    skipped_count = 0
    failed = []
    results = []

    for member in members:
        member_id = member["member_id"]

        try:
            result = issue_birthday_coupon(
                member_id,
                as_of=current,
            )
            results.append(result)

            if result.get("issued") is True:
                issued_count += 1
            elif result.get("reason") == "本年度生日禮已發送":
                existing_count += 1
            else:
                skipped_count += 1

        except Exception as error:
            failed.append({
                "member_id": member_id,
                "error": str(error),
            })

    return {
        "year": current.year,
        "month": current.month,
        "matched_members": len(members),
        "issued_count": issued_count,
        "existing_count": existing_count,
        "skipped_count": skipped_count,
        "failed_count": len(failed),
        "failed": failed,
        "results": results,
    }



def get_member_benefit(member_id):
    """
    依 members.vip 與 members.member_level 回傳會員權益。

    雲端第四週欄位已經有 vip、member_level，
    因此 VIP 5% 不需要新增資料表或修改其他組欄位。
    """
    try:
        member_id = int(member_id)
    except (TypeError, ValueError) as error:
        raise ValueError("member_id 必須是整數") from error

    if member_id <= 0:
        raise ValueError("member_id 必須大於 0")

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                member_id,
                name,
                vip,
                member_level
            FROM members
            WHERE member_id = %s
            LIMIT 1
            """,
            (member_id,),
        )

        member = cursor.fetchone()

        if member is None:
            raise ValueError("找不到會員")

        member_level = str(
            member.get("member_level") or ""
        ).strip().lower()

        eligible = (
            to_bool(member.get("vip"))
            and member_level == VIP_MEMBER_LEVEL
        )

        return {
            "member_id": member["member_id"],
            "name": member.get("name"),
            "vip": to_bool(member.get("vip")),
            "member_level": member_level,
            "eligible": eligible,
            "benefit_code": (
                VIP_BENEFIT_CODE
                if eligible
                else None
            ),
            "benefit_name": (
                "VIP 會員 5% 禮遇"
                if eligible
                else None
            ),
            "discount_type": (
                "percentage"
                if eligible
                else None
            ),
            "discount_value": (
                float(VIP_DISCOUNT_PERCENT)
                if eligible
                else 0.0
            ),
        }

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def calculate_member_discount(
    member_id,
    original_amount,
):
    """
    計算會員結帳金額。

    VIP 會員套用 5% 折扣；一般會員維持原價。
    此函式只回傳計算結果，不修改 total_amount 或訂單資料。
    """
    try:
        amount = Decimal(str(original_amount))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("original_amount 必須是有效金額") from error

    if amount < 0:
        raise ValueError("original_amount 不可小於 0")

    amount = amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    benefit = get_member_benefit(member_id)

    if benefit["eligible"]:
        discount_amount = (
            amount
            * VIP_DISCOUNT_PERCENT
            / Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    else:
        discount_amount = Decimal("0.00")

    final_amount = (
        amount - discount_amount
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return {
        **benefit,
        "original_amount": float(amount),
        "discount_amount": float(discount_amount),
        "final_amount": float(final_amount),
    }


def redeem_member_coupon(
    member_coupon_id,
    member_id,
):
    """
    核銷迎新禮或生日禮。

    抽獎券仍沿用 redeem_member_prize() 的 QR Code 流程，
    避免同一張抽獎券在兩套流程中產生狀態不一致。
    """
    try:
        member_coupon_id = int(member_coupon_id)
        member_id = int(member_id)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "member_coupon_id 與 member_id 必須是整數"
        ) from error

    if member_coupon_id <= 0 or member_id <= 0:
        raise ValueError(
            "member_coupon_id 與 member_id 必須大於 0"
        )

    conn = None
    cursor = None

    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                mc.member_coupon_id,
                mc.member_id,
                mc.source,
                mc.status,
                mc.used_time,
                c.coupon_name,
                c.status AS coupon_status,
                c.start_at,
                c.end_at
            FROM member_coupons AS mc
            JOIN coupons AS c
                ON c.coupon_id = mc.coupon_id
            WHERE mc.member_coupon_id = %s
              AND mc.member_id = %s
            FOR UPDATE
            """,
            (
                member_coupon_id,
                member_id,
            ),
        )

        coupon = cursor.fetchone()

        if coupon is None:
            conn.rollback()
            return {
                "success": False,
                "message": "找不到會員優惠券",
            }

        source = str(coupon.get("source") or "")

        is_direct_redeem_source = (
            source == REGISTRATION_WELCOME_COUPON_SOURCE
            or source.startswith(
                BIRTHDAY_COUPON_SOURCE_PREFIX
            )
        )

        if not is_direct_redeem_source:
            conn.rollback()
            return {
                "success": False,
                "message": "此優惠券需使用原本的抽獎核銷流程",
            }

        if coupon.get("status") == "used":
            conn.rollback()
            return {
                "success": False,
                "message": "此優惠券已使用",
            }

        if coupon.get("status") == "expired":
            conn.rollback()
            return {
                "success": False,
                "message": "此優惠券已過期",
            }

        if coupon.get("status") != "unused":
            conn.rollback()
            return {
                "success": False,
                "message": "此優惠券目前無法使用",
            }

        now = datetime.now()
        start_at = coupon.get("start_at")
        end_at = coupon.get("end_at")

        if coupon.get("coupon_status") != "active":
            conn.rollback()
            return {
                "success": False,
                "message": "此優惠券目前未啟用",
            }

        if start_at is not None and start_at > now:
            conn.rollback()
            return {
                "success": False,
                "message": "此優惠券尚未生效",
            }

        if end_at is not None and end_at < now:
            cursor.execute(
                """
                UPDATE member_coupons
                SET status = 'expired'
                WHERE member_coupon_id = %s
                  AND status = 'unused'
                """,
                (member_coupon_id,),
            )
            conn.commit()
            return {
                "success": False,
                "message": "此優惠券已過期",
            }

        cursor.execute(
            """
            UPDATE member_coupons
            SET
                status = 'used',
                used_time = CURRENT_TIMESTAMP
            WHERE member_coupon_id = %s
              AND member_id = %s
              AND status = 'unused'
            """,
            (
                member_coupon_id,
                member_id,
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError("更新優惠券使用狀態失敗")

        conn.commit()

        return {
            "success": True,
            "message": "優惠券核銷成功",
            "member_coupon_id": member_coupon_id,
            "member_id": member_id,
            "coupon_name": coupon.get("coupon_name"),
            "source": source,
        }

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_member_coupons(member_id=None, status=None, limit=100):
    """
    查詢會員優惠券資料。
    """
    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 100

        if limit > 500:
            limit = 500

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            mc.member_coupon_id,
            mc.member_id,
            m.name AS member_name,
            mc.coupon_id,
            c.coupon_name,
            c.description,
            c.discount_type,
            c.discount_value,
            c.start_at,
            c.end_at,
            c.status AS coupon_status,
            mc.source,
            mc.status,
            mc.receive_time,
            mc.used_time,
            mp.redeem_token,
            mp.status AS redemption_status,
            mp.expires_at AS redemption_expires_at
        FROM member_coupons mc
        JOIN members m
            ON mc.member_id = m.member_id
        JOIN coupons c
            ON mc.coupon_id = c.coupon_id
        LEFT JOIN member_prizes mp
            ON mp.member_prize_id = (
                SELECT matched_prize.member_prize_id
                FROM member_prizes AS matched_prize
                WHERE matched_prize.member_id = mc.member_id
                  AND matched_prize.campaign_code = mc.source
                ORDER BY
                    ABS(TIMESTAMPDIFF(
                        SECOND,
                        matched_prize.issued_at,
                        mc.receive_time
                    )) ASC,
                    matched_prize.member_prize_id DESC
                LIMIT 1
            )
        WHERE 1 = 1
        """

        params = []

        if member_id is not None:
            sql += " AND mc.member_id = %s"
            params.append(member_id)

        if status:
            sql += " AND mc.status = %s"
            params.append(status)

        sql += """
        ORDER BY mc.receive_time DESC,
                 mc.member_coupon_id DESC
        LIMIT %s
        """
        params.append(limit)

        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    except (TypeError, ValueError):
        print("取得會員優惠券失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得會員優惠券失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_member_non_coupon_prizes(member_id, limit=100):
    """Return redeemable lottery prizes which are not backed by coupons."""
    conn = None
    cursor = None
    try:
        limit = max(1, min(int(limit), 500))
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                mp.member_prize_id,
                mp.prize_code,
                mp.redeem_token,
                mp.status,
                mp.issued_at,
                mp.expires_at,
                mp.redeemed_at,
                lp.prize_name,
                lp.prize_type,
                lp.prize_value
            FROM member_prizes AS mp
            JOIN lottery_prizes AS lp
                ON lp.prize_id = mp.prize_id
            WHERE mp.member_id = %s
              AND lp.coupon_id IS NULL
            ORDER BY mp.issued_at DESC, mp.member_prize_id DESC
            LIMIT %s
            """,
            (member_id, limit),
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_coupon_summary():
    """
    取得優惠券統計資料。
    """
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            (SELECT COUNT(*) FROM coupons) AS total_coupons,

            (
                SELECT COUNT(*)
                FROM coupons
                WHERE status = 'active'
                  AND (start_at IS NULL OR start_at <= NOW())
                  AND (end_at IS NULL OR end_at >= NOW())
            ) AS active_coupons,

            (SELECT COUNT(*) FROM member_coupons) AS total_issued,

            (
                SELECT COUNT(*)
                FROM member_coupons
                WHERE status = 'unused'
            ) AS unused_count,

            (
                SELECT COUNT(*)
                FROM member_coupons
                WHERE status = 'used'
            ) AS used_count,

            (
                SELECT COUNT(*)
                FROM member_coupons
                WHERE status = 'expired'
            ) AS expired_count
        """

        cursor.execute(sql)
        summary = cursor.fetchone()

        return summary or {
            "total_coupons": 0,
            "active_coupons": 0,
            "total_issued": 0,
            "unused_count": 0,
            "used_count": 0,
            "expired_count": 0
        }

    except Exception as e:
        print("取得優惠券統計失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_seven_day_visit_trend():
    """
    取得最近 7 天到店趨勢。
    """
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            DATE(visit_time) AS visit_date,
            COUNT(*) AS total_visits,
            SUM(CASE WHEN subject_type = 'member' THEN 1 ELSE 0 END)
                AS member_visits,
            SUM(CASE WHEN subject_type = 'visitor' THEN 1 ELSE 0 END)
                AS visitor_visits
        FROM recognition_logs
        WHERE visit_time >= CURDATE() - INTERVAL 6 DAY
          AND visit_time < CURDATE() + INTERVAL 1 DAY
        GROUP BY DATE(visit_time)
        ORDER BY visit_date ASC
        """

        cursor.execute(sql)
        return cursor.fetchall()

    except Exception as e:
        print("取得最近 7 天到店趨勢失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_visit_hour_distribution():
    """
    取得到店時段分布。
    """
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            HOUR(visit_time) AS visit_hour,
            COUNT(*) AS total_visits,
            SUM(CASE WHEN subject_type = 'member' THEN 1 ELSE 0 END)
                AS member_visits,
            SUM(CASE WHEN subject_type = 'visitor' THEN 1 ELSE 0 END)
                AS visitor_visits
        FROM recognition_logs
        WHERE visit_time IS NOT NULL
        GROUP BY HOUR(visit_time)
        ORDER BY visit_hour ASC
        """

        cursor.execute(sql)
        return cursor.fetchall()

    except Exception as e:
        print("取得到店時段分布失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_top_visitors(limit=10):
    """
    取得來店次數最多的散客排行。
    """
    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 10

        if limit > 100:
            limit = 100

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            visitor_id,
            visitor_code,
            display_name,
            visitor_visit_count,
            first_seen_at,
            last_seen_at,
            best_face_image
        FROM visitors
        WHERE visitor_visit_count > 0
        ORDER BY visitor_visit_count DESC,
                 last_seen_at DESC,
                 visitor_id ASC
        LIMIT %s
        """

        cursor.execute(sql, (limit,))
        return cursor.fetchall()

    except (TypeError, ValueError):
        print("取得散客排行失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得散客排行失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_monthly_visit_ranking(limit=10):
    """
    取得本月會員來店排行。
    """
    conn = None
    cursor = None

    try:
        limit = int(limit)

        if limit <= 0:
            limit = 10

        if limit > 100:
            limit = 100

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            m.member_id,
            m.name,
            m.vip,
            m.member_level,
            COUNT(rl.log_id) AS monthly_visit_count,
            COALESCE(SUM(rl.stay_seconds), 0) AS monthly_stay_seconds,
            ROUND(
                COALESCE(SUM(rl.stay_seconds), 0) / 60.0,
                2
            ) AS monthly_stay_minutes,
            MAX(rl.visit_time) AS last_visit_time
        FROM members m
        JOIN recognition_logs rl
            ON rl.member_id = m.member_id
           AND rl.subject_type = 'member'
        WHERE rl.visit_time >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
          AND rl.visit_time < DATE_FORMAT(
                CURDATE() + INTERVAL 1 MONTH,
                '%Y-%m-01'
              )
        GROUP BY
            m.member_id,
            m.name,
            m.vip,
            m.member_level
        ORDER BY
            monthly_visit_count DESC,
            monthly_stay_seconds DESC,
            m.member_id ASC
        LIMIT %s
        """

        cursor.execute(sql, (limit,))
        rows = cursor.fetchall()

        for row in rows:
            row["member_level_text"] = get_member_level_text(
                row.get("member_level")
            )

        return rows

    except (TypeError, ValueError):
        print("取得本月來店排行失敗：limit 必須是整數")
        raise

    except Exception as e:
        print("取得本月來店排行失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


def get_latest_unconverted_visitor():
    """
    取得最近一次尚未轉會員的 Visitor。
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                rl.visitor_id,
                v.visitor_code
            FROM recognition_logs rl
            JOIN visitors v
              ON rl.visitor_id = v.visitor_id
            WHERE rl.subject_type='visitor'
              AND rl.visitor_id IS NOT NULL
              AND v.converted_member_id IS NULL
            ORDER BY rl.visit_time DESC
            LIMIT 1
        """)

        return cursor.fetchone()

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
