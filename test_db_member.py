from database.db import (
    get_connection,
    get_member_by_id,
    save_recognition_log,
    insert_vip_notification
)


def test_insert_member():
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO members (
        name,
        phone,
        vip,
        member_level,
        visit_count,
        line_user_id,
        total_amount,
        favorite_product,
        face_image
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    data = (
        "test_member",
        "0912345678",
        True,
        "VIP",
        5,
        "Utest123",
        1500,
        "拿鐵",
        "test.jpg"
    )

    cursor.execute(sql, data)
    conn.commit()

    member_id = cursor.lastrowid
    print("新增會員成功，member_id =", member_id)

    cursor.close()
    conn.close()

    return member_id


def test_get_member_by_id(member_id):
    member = get_member_by_id(member_id)
    print("查詢會員結果：", member)
    return member


def test_save_recognition_log(member):
    data = {
        "member_id": member["member_id"],
        "name": member["name"],
        "vip": member["vip"],
        "line_user_id": member["line_user_id"],
        "confidence": 0.88,

        "camera_id": "camera_01",
        "member_level": member["member_level"],
        "recognition_status": "recognized",
        "visit_status": "visit",
        "visit_time": "2026-07-10 19:30:00",
        "leave_time": None,
        "stay_minutes": 0,

        "recognized_at": "2026-07-10 19:30:00",
        "created_at": "2026-07-10 19:30:00",
        "camera_location": "entrance_camera"
    }

    log_id = save_recognition_log(data)
    print("新增辨識紀錄成功，log_id =", log_id)

    return log_id

def test_insert_vip_notification(member, log_id):
    notification_id = insert_vip_notification(
        member_id=member["member_id"],
        log_id=log_id,
        line_user_id=member["line_user_id"],
        message=f"VIP 會員 {member['name']} 到店",
        status="sent"
    )

    print("新增 VIP 通知成功，notification_id =", notification_id)

    return notification_id


if __name__ == "__main__":
    member_id = test_insert_member()

    member = test_get_member_by_id(member_id)

    log_id = test_save_recognition_log(member)

    notification_id = test_insert_vip_notification(member, log_id)

    print("資料庫函式測試完成")