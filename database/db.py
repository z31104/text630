import mysql.connector
from dotenv import load_dotenv

load_dotenv()



def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="f129659029",
        database="smart_member_system"
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


def get_member_by_id(member_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT member_id, name, phone, email, vip, line_id
        FROM members
        WHERE member_id = %s
        """,
        (member_id,)
    )

    member = cursor.fetchone()

    cursor.close()
    conn.close()

    if member:
        member["member_level"] = "VIP" if member["vip"] else "normal"
        member["line_user_id"] = member["line_id"]

    return member

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


def save_recognition_log(data):
    return insert_recognition_log(
        member_id=data.get("member_id"),
        name=data.get("name"),
        vip=data.get("vip", False),
        line_id=data.get("line_id") or data.get("line_user_id"),
        confidence=data.get("confidence", 0),
        recognized_at=data.get("recognized_at") or data.get("recognition_time"),
        camera_location=data.get("camera_location")
    )


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