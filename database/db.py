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
        database=clean_env(os.getenv("DB_NAME", "smart_member_system"))
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
    camera_id=None,
    confidence=0,
    member_level=None,
    recognition_status=None,
    visit_status=None,
    visit_time=None,
    leave_time=None,
    stay_minutes=None
):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO recognition_logs (
        member_id,
        camera_id,
        confidence,
        member_level,
        recognition_status,
        visit_status,
        visit_time,
        leave_time,
        stay_minutes
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    data = (
        member_id,
        camera_id,
        confidence,
        member_level,
        recognition_status,
        visit_status,
        visit_time,
        leave_time,
        stay_minutes
    )

    cursor.execute(sql, data)
    conn.commit()

    log_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return log_id


def save_recognition_log(data):
    return insert_recognition_log(
        member_id=data.get("member_id"),
        camera_id=data.get("camera_id"),
        confidence=data.get("confidence", 0),
        member_level=data.get("member_level"),
        recognition_status=data.get("recognition_status"),
        visit_status=data.get("visit_status"),
        visit_time=data.get("visit_time"),
        leave_time=data.get("leave_time"),
        stay_minutes=data.get("stay_minutes")
    )


def insert_vip_notification(member_id, log_id, line_user_id, message, status="sent"):
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

    notification_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return notification_id