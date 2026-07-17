import os
import mysql.connector
import json
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()


# 辨識狀態
RECOGNITION_STATUS_RECOGNIZED = "recognized"
RECOGNITION_STATUS_GUEST = "guest"
RECOGNITION_STATUS_FAILED = "failed"

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

# VIP 通知狀態
NOTIFICATION_STATUS_PENDING = "pending"
NOTIFICATION_STATUS_SENT = "sent"
NOTIFICATION_STATUS_FAILED = "failed"


def clean_env(value):
    if value is None:
        return None
    return value.replace('"', '').replace("'", "")




def get_connection():
    # Cloud Run
    if os.getenv("INSTANCE_CONNECTION_NAME"):
        return mysql.connector.connect(
            user=clean_env(os.getenv("DB_USER")),
            password=clean_env(os.getenv("DB_PASSWORD")),
            database=clean_env(os.getenv("DB_NAME")),
            unix_socket=f"/cloudsql/{clean_env(os.getenv('INSTANCE_CONNECTION_NAME'))}"
        )

    # 本機
    return mysql.connector.connect(
        host=clean_env(os.getenv("DB_HOST", "localhost")),
        port=int(clean_env(os.getenv("DB_PORT", "3306"))),
        user=clean_env(os.getenv("DB_USER", "root")),
        password=clean_env(os.getenv("DB_PASSWORD", "")),
        database=clean_env(os.getenv("DB_NAME", "smart_member_system"))
    )


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
            visit_count,
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
            visit_count,
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


def insert_recognition_log(
    member_id=None,
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
    stay_minutes=0,
    created_at=None
):
    conn = None
    cursor = None

    try:
        # 如果沒有 member_id，視為 Guest
        if member_id is None:
            if name is None:
                name = "Guest"

            vip = False
            member_level = "guest"

            if recognition_status == RECOGNITION_STATUS_RECOGNIZED:
                recognition_status = RECOGNITION_STATUS_GUEST
        
        # 1. 檢查 recognition_status 是否合法
        valid_recognition_statuses = {
            RECOGNITION_STATUS_RECOGNIZED,
            RECOGNITION_STATUS_GUEST,
            RECOGNITION_STATUS_FAILED
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

        # 3. 沒有傳時間時，自動補現在時間
        if recognized_at is None:
            recognized_at = datetime.now()

        if created_at is None:
            created_at = datetime.now()

        if visit_time is None:
            visit_time = recognized_at

        # 4. 檢查通過後，才連線資料庫
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO recognition_logs (
            member_id,
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
            stay_minutes,
            recognized_at,
            created_at,
            camera_location
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        data = (
            member_id,
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
            stay_minutes,
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
        member_id=data.get("member_id"),
        name=data.get("name"),
        vip=data.get("vip", False),
        line_user_id=data.get("line_user_id"),
        confidence=data.get("confidence", 0),
        recognized_at=data.get("recognized_at") or data.get("recognition_time"),
        camera_location=data.get("camera_location"),

        camera_id=data.get("camera_id"),
        member_level=data.get("member_level"),
        recognition_status=(data.get("recognition_status") or RECOGNITION_STATUS_RECOGNIZED),
        visit_status=(  data.get("visit_status") or VISIT_STATUS_ARRIVED),
        visit_time=data.get("visit_time"),
        last_seen_at=data.get("last_seen_at"),
        leave_time=data.get("leave_time"),
        stay_seconds=data.get("stay_seconds", 0),
        stay_minutes=data.get("stay_minutes", 0),
        created_at=data.get("created_at")
    )

def insert_vip_notification(
    member_id,
    log_id,
    line_user_id,
    message,
    status="pending"
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
            status
        )
        VALUES (%s, %s, %s, %s, %s)
        """

        data = (
            member_id,
            log_id,
            line_user_id,
            message,
            status
        )

        cursor.execute(sql, data)
        conn.commit()

        return cursor.lastrowid

    except mysql.connector.IntegrityError as e:
        if conn:
            conn.rollback()

        # 1062：同一個 log_id 已經有通知
        if e.errno == 1062:
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
    查詢指定對象目前尚未結束的到店紀錄。

    目前 recognition_logs 已有 member_id，
    所以先正式支援 member。

    visitor 需要等 recognition_logs 加入 visitor_id 後，
    再補上 visitor 查詢。
    """

    conn = None
    cursor = None

    try:
        if subject_type not in ("member", "visitor"):
            return None

        if subject_id is None:
            return None

        # 目前 recognition_logs 還沒有 visitor_id
        if subject_type == "visitor":
            return None

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            log_id,
            member_id,
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
            stay_minutes,
            camera_location,
            created_at
        FROM recognition_logs
        WHERE member_id = %s
          AND leave_time IS NULL
          AND visit_status IN (%s, %s)
        """

        params = [
            subject_id,
            VISIT_STATUS_ARRIVED,
            VISIT_STATUS_STAYING
        ]

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
        print("查詢 active visit 失敗：", e)
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
        """

        cursor.execute(
            sql,
            (
                last_seen_at,
                RECOGNITION_STATUS_RECOGNIZED,
                VISIT_STATUS_STAYING,
                log_id
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


def close_recognition_visit(
    log_id,
    last_seen_at,
    leave_time,
    stay_seconds,
    stay_minutes
):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        UPDATE recognition_logs
        SET
            recognition_status = %s,
            visit_status = %s,
            last_seen_at = %s,
            leave_time = %s,
            stay_seconds = %s,
            stay_minutes = %s
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
                stay_minutes,
                log_id,
                VISIT_STATUS_ARRIVED,
                VISIT_STATUS_STAYING,
            )
        )

        closed_count = cursor.rowcount
        
        if closed_count == 1:
            cursor.execute(
                """
                UPDATE members
                SET visit_count = COALESCE(visit_count, 0) + 1
                WHERE member_id = (
                SELECT member_id
                FROM recognition_logs
                WHERE log_id = %s
                )
                AND member_id IS NOT NULL
                """,
                (log_id,)
            )
            
        conn.commit()
        return closed_count


    except Exception as e:
        if conn:
            conn.rollback()

        print("更新會員離店紀錄失敗：", e)
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
    visit_count=0,
    line_user_id=None,
    total_amount=0,
    favorite_product=None,
    face_image=None,
    registration_source="line"
):
    conn = None
    cursor = None

    try:
        vip = bool(vip)
        member_level = "vip" if vip else "normal"

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
INSERT INTO members (
    name,
    phone,
    birthday,
    vip,
    member_level,
    visit_count,
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
        visit_count,
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

        if encoding_data is None:
            raise ValueError("encoding_data 不可為空")

        # 支援 NumPy array
        if hasattr(encoding_data, "tolist"):
            encoding_data = encoding_data.tolist()

        # 如果是 Python list，先檢查是否為 128 維
        if isinstance(encoding_data, (list, tuple)):
            if len(encoding_data) != 128:
                raise ValueError(
                    f"encoding_data 必須是 128 維，目前為 {len(encoding_data)} 維"
                )

            encoding_data = json.dumps(
                list(encoding_data),
                ensure_ascii=False
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
    line_user_id=None,
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

        vip = bool(vip)
        member_level = "vip" if vip else "normal"
              
        # NumPy array 轉成 Python list
        if hasattr(encoding_data, "tolist"):
            encoding_data = encoding_data.tolist()

        # 檢查人臉特徵是否為 128 維
        if isinstance(encoding_data, (list, tuple)):
            if len(encoding_data) != 128:
                raise ValueError(
                    f"encoding_data 必須是 128 維，目前為 {len(encoding_data)} 維"
                )

            encoding_data = json.dumps(
                list(encoding_data),
                ensure_ascii=False
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
            line_user_id,
            face_image,
            registration_source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            member_sql,
            (
                name,
                phone,
                birthday,  
                vip,
                member_level,
                line_user_id,
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

        # 兩個都成功才提交
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
            m.vip,
            m.member_level,
            m.visit_count,
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