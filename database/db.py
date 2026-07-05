import mysql.connector


def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        port=3307,
        user="root",
        password="root",
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


def insert_recognition_log(member_id, name, vip, confidence):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO recognition_logs (member_id, name, vip, confidence)
    VALUES (%s, %s, %s, %s)
    """

    data = (
        member_id,
        name,
        vip,
        confidence
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
    INSERT INTO vip_notifications (member_id, log_id, line_id, message, status)
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