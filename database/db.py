import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 8625)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "smart_member_system")
    )

    return conn


def get_all_members():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT member_id, name, vip, line_id FROM members")
    members = cursor.fetchall()

    cursor.close()
    conn.close()

    return members


def insert_recognition_log(
    member_id,
    name,
    vip,
    line_id=None,
    confidence=0,
    recognized_at=None,
    camera_location=None
):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO recognition_logs
    (member_id, name, vip, line_id, confidence, recognized_at, camera_location)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    data = (
        member_id,
        name,
        vip,
        line_id,
        confidence,
        recognized_at,
        camera_location
    )

    cursor.execute(sql, data)
    conn.commit()

    log_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return log_id


def insert_vip_notification(member_id, log_id, line_id, message, status="sent"):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO vip_notifications
    (member_id, log_id, line_id, message, status)
    VALUES (%s, %s, %s, %s, %s)
    """

    data = (
        member_id,
        log_id,
        line_id,
        message,
        status
    )

    cursor.execute(sql, data)
    conn.commit()

    notification_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return notification_id