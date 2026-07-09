from flask import Blueprint, request, redirect, jsonify
from database.db import get_connection

member_bp = Blueprint("member", __name__)


@member_bp.route("/member")
def member():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT member_id, name, vip, line_id FROM members")
    db_members = cursor.fetchall()

    cursor.close()
    conn.close()

    html = """
    <h1>會員資料頁</h1>
    <p><a href="/member/add">新增會員</a></p>

    <table border="1" cellpadding="8">
        <tr>
            <th>會員編號</th>
            <th>姓名</th>
            <th>VIP</th>
            <th>LINE ID</th>
            <th>圖片</th>
            <th>操作</th>
        </tr>
    """

    for m in db_members:
        member_id = m["member_id"]

        html += f"""
        <tr>
            <td>{m["member_id"]}</td>
            <td>{m["name"]}</td>
            <td>{"是" if m["vip"] else "否"}</td>
            <td>{m["line_id"]}</td>
            <td>-</td>
            <td>
                <a href="/member/edit/{member_id}">修改</a>
                <a href="/member/delete/{member_id}">刪除</a>
            </td>
        </tr>
        """

    html += """
    </table>
    """

    return html


@member_bp.route("/member/recognition_log", methods=["POST"])
def add_recognition_log():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "請傳入 JSON 格式資料"}), 400

    member_id = data.get("member_id")
    name = data.get("name")
    vip = data.get("vip", False)
    line_id = data.get("line_id")
    confidence = data.get("confidence", 0)
    recognized_at = data.get("recognized_at")
    camera_location = data.get("camera_location")

    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO recognition_logs
    (member_id, name, vip, line_id, confidence, recognized_at, camera_location)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        member_id,
        name,
        vip,
        line_id,
        confidence,
        recognized_at,
        camera_location
    )

    cursor.execute(sql, values)
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({
        "message": "辨識紀錄新增成功",
        "member_id": member_id,
        "name": name,
        "vip": vip,
        "line_id": line_id,
        "confidence": confidence,
        "recognized_at": recognized_at,
        "camera_location": camera_location
    })


@member_bp.route("/member/add", methods=["GET", "POST"])
def add_member_page():
    if request.method == "POST":
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO members (name, phone, email, vip, line_id)
        VALUES (%s, %s, %s, %s, %s)
        """

        data = (
            request.form.get("name"),
            request.form.get("phone"),
            request.form.get("email"),
            request.form.get("vip") == "1",
            request.form.get("line_id")
        )

        cursor.execute(sql, data)
        conn.commit()

        cursor.close()
        conn.close()

        return redirect("/member")

    return """
    <h1>新增會員</h1>

    <form method="POST">
        <p>姓名：<input type="text" name="name"></p>
        <p>電話：<input type="text" name="phone"></p>
        <p>Email：<input type="text" name="email"></p>
        <p>LINE ID：<input type="text" name="line_id"></p>
        <p>是否 VIP：
            <select name="vip">
                <option value="0">一般會員</option>
                <option value="1">VIP會員</option>
            </select>
        </p>
        <button type="submit">新增會員</button>
    </form>

    <p><a href="/member">回會員列表</a></p>
    """


@member_bp.route("/member/delete/<int:member_id>")
def delete_member(member_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM vip_notifications WHERE member_id = %s", (member_id,))
    cursor.execute("DELETE FROM recognition_logs WHERE member_id = %s", (member_id,))
    cursor.execute("DELETE FROM face_images WHERE member_id = %s", (member_id,))
    cursor.execute("DELETE FROM members WHERE member_id = %s", (member_id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/member")

@member_bp.route("/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT member_id, name, phone, email, vip, line_id FROM members WHERE member_id = %s",
        (member_id,)
    )
    target_member = cursor.fetchone()

    if target_member is None:
        cursor.close()
        conn.close()
        return "找不到會員"

    if request.method == "POST":
        sql = """
        UPDATE members
        SET name = %s, phone = %s, email = %s, vip = %s, line_id = %s
        WHERE member_id = %s
        """

        data = (
            request.form.get("name"),
            request.form.get("phone"),
            request.form.get("email"),
            request.form.get("vip") == "1",
            request.form.get("line_id"),
            member_id
        )

        cursor.execute(sql, data)
        conn.commit()

        cursor.close()
        conn.close()

        return redirect("/member")

    cursor.close()
    conn.close()

    vip_selected = "selected" if target_member["vip"] else ""
    normal_selected = "" if target_member["vip"] else "selected"

    return f"""
    <h1>修改會員</h1>

    <form method="POST">
        <p>會員編號：{target_member['member_id']}</p>
        <p>姓名：<input type="text" name="name" value="{target_member['name'] or ''}"></p>
        <p>電話：<input type="text" name="phone" value="{target_member['phone'] or ''}"></p>
        <p>Email：<input type="text" name="email" value="{target_member['email'] or ''}"></p>
        <p>LINE ID：<input type="text" name="line_id" value="{target_member['line_id'] or ''}"></p>
        <p>是否 VIP：
            <select name="vip">
                <option value="0" {normal_selected}>一般會員</option>
                <option value="1" {vip_selected}>VIP會員</option>
            </select>
        </p>
        <button type="submit">儲存修改</button>
    </form>

    <p><a href="/member">回會員列表</a></p>
    """