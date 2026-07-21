import os
import mysql.connector
import json
import random
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
    stay_minutes=0,
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
            vip = False
            member_level = "guest"

            if name is None:
                name = visitor_code or "Visitor"

        else:
            member_id = None
            visitor_id = None
            visitor_code = None
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
            stay_minutes,
            recognized_at,
            created_at,
            camera_location
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            stay_minutes,
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
                            visit_count =
                                COALESCE(visit_count, 0) + 1,

                                
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
            m.birthday,
            m.vip,
            m.member_level,
            m.total_visit_count,
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
            visit_count,
            first_seen_at,
            last_seen_at,
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

        if encoding_data is None:
            raise ValueError("encoding_data 不可為空")

        if hasattr(encoding_data, "tolist"):
            encoding_data = encoding_data.tolist()

        if isinstance(encoding_data, (list, tuple)):
            if len(encoding_data) != 128:
                raise ValueError(
                    f"encoding_data 必須是 128 維，目前為 "
                    f"{len(encoding_data)} 維"
                )

            encoding_data = json.dumps(
                list(encoding_data),
                ensure_ascii=False
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
            visit_count,
            first_seen_at,
            last_seen_at
        )
        VALUES (%s, %s, %s, %s, %s)
        """

        cursor.execute(
            visitor_sql,
            (
                visitor_code,
                display_name,
                0,
                first_seen_at,
                last_seen_at
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
            v.visit_count,
            v.first_seen_at,
            v.last_seen_at,
            v.created_at AS visitor_created_at,
            v.updated_at AS visitor_updated_at
        FROM visitor_faces vf
        JOIN visitors v
            ON vf.visitor_id = v.visitor_id
        WHERE vf.encoding_data IS NOT NULL
          AND vf.encoding_data <> ''
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
    查詢 Dashboard 統計資料。
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
            ) AS today_visits,

            (
                SELECT COUNT(*)
                FROM recognition_logs
                WHERE DATE(visit_time) = CURDATE()
                  AND subject_type = 'member'
                  AND vip = TRUE
            ) AS today_vip,

            (
                SELECT COUNT(*)
                FROM members
                WHERE DATE(created_at) = CURDATE()
            ) AS new_members,

            (
                SELECT COUNT(*)
                FROM recognition_logs
                WHERE DATE(visit_time) = CURDATE()
                  AND subject_type = 'visitor'
            ) AS visitors
        """

        cursor.execute(sql)
        summary = cursor.fetchone()

        if summary is None:
            return {
                "today_visits": 0,
                "today_vip": 0,
                "new_members": 0,
                "visitors": 0
            }

        return summary

    except Exception as e:
        print("取得 Dashboard 統計失敗：", e)
        raise

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
            log_id,
            subject_type,
            member_id,
            visitor_id,
            visitor_code,
            name,
            vip,
            member_level,
            confidence,
            recognition_status,
            visit_status,
            camera_id,
            camera_location,
            visit_time,
            recognized_at,
            last_seen_at,
            leave_time,
            stay_seconds,
            stay_minutes,
            created_at
        FROM recognition_logs
        ORDER BY recognized_at DESC, log_id DESC
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
    is_final=True
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
            redeemed,
            redeemed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL)
        """

        cursor.execute(
            sql,
            (
                member_id,
                prize_id,
                coupon_id,
                prize_name,
                result,
                bool(is_final)
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
                lottery_id,
                member_id,
                prize_id,
                prize_name,
                result,
                is_final,
                created_at
            FROM lottery_records
            WHERE member_id = %s
              AND is_final = TRUE
            ORDER BY created_at DESC,
                     lottery_id DESC
            LIMIT 1
            """,
            (member_id,)
        )

        completed_record = cursor.fetchone()

        if completed_record is not None:
            conn.rollback()

            return {
                "success": False,
                "message": "這位會員已經完成抽獎",
                "already_completed": True,
                "record": completed_record
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
                prize_status
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

        prize_id = selected_prize["prize_id"]
        prize_name = selected_prize["prize_name"]
        prize_type = selected_prize["prize_type"]

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
                prize_name,
                result,
                is_final,
                redeemed,
                redeemed_at
            )
            VALUES (
                %s,
                %s,
                NULL,
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
                prize_name,
                prize_name,
                bool(is_final)
            )
        )

        lottery_id = cursor.lastrowid

        # -------------------------------------------------
        # 第 7 步：全部成功後才 commit
        # -------------------------------------------------
        conn.commit()

        return {
            "success": True,
            "message": "抽獎成功",
            "already_completed": False,
            "lottery_id": lottery_id,
            "is_final": bool(is_final),
            "prize": selected_prize
        }

    except (TypeError, ValueError) as e:
        if conn:
            conn.rollback()

        print("抽獎失敗：", e)

        return {
            "success": False,
            "message": str(e),
            "already_completed": False
        }

    except Exception as e:
        if conn:
            conn.rollback()

        print("抽獎處理失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()
