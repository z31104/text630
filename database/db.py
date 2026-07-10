import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def clean_env(value):
    if value is None:
        return None
    return value.replace('"', '').replace("'", "")


def get_connection():
    conn = mysql.connector.connect(
        host=clean_env(os.getenv("DB_HOST", "localhost")),
        port=int(clean_env(os.getenv("DB_PORT", "3306"))),
        user=clean_env(os.getenv("DB_USER", "root")),
        password=clean_env(os.getenv("DB_PASSWORD", "")),
        database=clean_env(os.getenv("DB_NAME", "smart_member_system")),
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci"
    )
    return conn


def get_all_members():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            member_id,
            name,
            phone,
            vip,
            member_level,
            visit_count,
            line_user_id,
            total_amount,
            favorite_product,
            face_image,
            created_at,
            updated_at
        FROM members
    """)

    members = cursor.fetchall()

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
            vip,
            member_level,
            visit_count,
            line_user_id,
            total_amount,
            favorite_product,
            face_image,
            created_at,
            updated_at
        FROM members
        WHERE member_id = %s
        """,
        (member_id,)
    )

    member = cursor.fetchone()

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
    recognition_status=None,
    visit_status=None,
    visit_time=None,
    leave_time=None,
    stay_minutes=0,
    created_at=None
):
    conn = None
    cursor = None

    try:
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
            leave_time,
            stay_minutes,
            recognized_at,
            created_at,
            camera_location
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            leave_time,
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
        recognition_status=data.get("recognition_status"),
        visit_status=data.get("visit_status"),
        visit_time=data.get("visit_time"),
        leave_time=data.get("leave_time"),
        stay_minutes=data.get("stay_minutes", 0),
        created_at=data.get("created_at")
    )

def insert_vip_notification(member_id, log_id, line_user_id, message, status="sent"):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO vip_notifications
        (member_id, log_id, line_user_id, message, status)
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

    except Exception as e:
        if conn:
            conn.rollback()

        print("新增 vip_notifications 失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()