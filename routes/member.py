import os
import uuid

from flask import Blueprint, request, redirect, jsonify
from werkzeug.utils import secure_filename

from database.db import get_connection, save_recognition_log

# 請依照你專案實際資料夾位置調整
from services.face_service import (
    validate_member_face_image,
    register_member_face
)

member_bp = Blueprint("member", __name__)

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

MEMBER_IMAGE_DIR = os.path.join(
    BASE_DIR,
    "member_images"
)

os.makedirs(
    MEMBER_IMAGE_DIR,
    exist_ok=True
)

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png"
}

def allowed_image_file(filename):
    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_IMAGE_EXTENSIONS

@member_bp.route("/member")
def member():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT member_id, name, phone, birthday, vip, member_level,
               visit_count, line_user_id, total_amount,
               favorite_product, face_image, registration_source,
                    created_at , updated_at
        FROM members
    """)
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
            <th>電話</th>
            <th>生日</th>
            <th>VIP</th>
            <th>會員等級</th>
            <th>來店次數</th>
            <th>LINE User ID</th>
            <th>累積消費</th>
            <th>偏好商品</th>
            <th>人臉圖片</th>
            <th>註冊來源</th>
            <th>操作</th>
        </tr>
    """

    for m in db_members:
        member_id = m["member_id"]
        
        member_level_text = {
            "vip": "VIP 會員",
            "normal": "一般會員",
            "guest": "陌生客"
        }.get(m["member_level"], "未知")

        html += f"""

        <tr>
            <td>{m["member_id"]}</td>
            <td>{m["name"]}</td>
            <td>{m["phone"] or ""}</td>
            <td>{m["birthday"] or ""}</td>
            <td>{"是" if m["vip"] else "否"}</td>
            <td>{m["member_level"] or ""}</td>
            <td>{m["visit_count"]}</td>
            <td>{m["line_user_id"] or ""}</td>
            <td>{m["total_amount"]}</td>
            <td>{m["favorite_product"] or ""}</td>
            <td>{m["face_image"] or ""}</td>
            <td>{m["registration_source"] or ""}</td>
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

    try:
        log_id = save_recognition_log(data)

        return jsonify({
            "message": "辨識紀錄新增成功",
            "log_id": log_id,
            "data": data
        })

    except Exception as e:
        return jsonify({
            "error": "辨識紀錄新增失敗",
            "detail": str(e)
        }), 500

   

@member_bp.route("/member/add", methods=["GET", "POST"])
def add_member_page():
    if request.method == "POST":
        conn = None
        cursor = None
        saved_image_path = None

        try:
            # 1. 接收上傳照片
            image_file = request.files.get("face_image")

            if image_file is None or image_file.filename == "":
                return "請選擇會員照片", 400

            # 2. 檢查圖片格式
            if not allowed_image_file(image_file.filename):
                return "照片格式錯誤，只接受 jpg、jpeg、png", 400

            # 3. 產生不重複的照片檔名
            original_filename = secure_filename(
                image_file.filename
            )

            extension = original_filename.rsplit(
                ".",
                1
            )[1].lower()

            new_filename = (
                f"member_{uuid.uuid4().hex}.{extension}"
            )

            saved_image_path = os.path.join(
                MEMBER_IMAGE_DIR,
                new_filename
            )

            # 4. 把照片存到 member_images
            image_file.save(saved_image_path)

            # 5. 先驗證照片是否只有一張人臉
            face_check_result = validate_member_face_image(
                saved_image_path
            )

            if not face_check_result.get("success"):
                if os.path.exists(saved_image_path):
                    os.remove(saved_image_path)

                return (
                    face_check_result.get(
                        "message",
                        "會員照片驗證失敗"
                    ),
                    400
                )

            # 6. 取得會員欄位
            vip = request.form.get("vip") == "1"
            member_level = "vip" if vip else "normal"

            conn = get_connection()
            cursor = conn.cursor()

            # 7. 先新增 members
            sql = """
            INSERT INTO members
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
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """

            data = (
                request.form.get("name"),
                request.form.get("phone"),
                request.form.get("birthday") or None,
                vip,
                member_level,
                int(request.form.get("visit_count") or 0),
                request.form.get("line_user_id"),
                int(request.form.get("total_amount") or 0),
                request.form.get("favorite_product"),
                saved_image_path,
                "backend"
            )

            cursor.execute(sql, data)

            # 8. 取得剛新增會員的 member_id
            member_id = cursor.lastrowid

            conn.commit()

            cursor.close()
            cursor = None

            conn.close()
            conn = None

            # 9. 寫入 face_images 並重新載入 AI 名單
            face_register_result = register_member_face(
                member_id=member_id,
                image_path=saved_image_path
            )

            if not face_register_result.get("success"):
                # 人臉建檔失敗時，移除剛建立的會員
                cleanup_conn = get_connection()
                cleanup_cursor = cleanup_conn.cursor()

                cleanup_cursor.execute(
                    """
                    DELETE FROM members
                    WHERE member_id = %s
                    """,
                    (member_id,)
                )

                cleanup_conn.commit()
                cleanup_cursor.close()
                cleanup_conn.close()

                if os.path.exists(saved_image_path):
                    os.remove(saved_image_path)

                return (
                    face_register_result.get(
                        "message",
                        "會員人臉建檔失敗"
                    ),
                    500
                )

            return redirect("/member")

        except Exception as e:
            if conn is not None:
                conn.rollback()

            if saved_image_path:
                if os.path.exists(saved_image_path):
                    os.remove(saved_image_path)

            return f"新增會員失敗：{e}", 500

        finally:
            if cursor is not None:
                cursor.close()

            if conn is not None:
                conn.close()

    return """
    <h1>新增會員</h1>

    <form method="POST" enctype="multipart/form-data">
        <p>
            姓名：
            <input
                type="text"
                name="name"
                required
            >
        </p>

        <p>
            電話：
            <input
                type="text"
                name="phone"
            >
        </p>

        <p>
            生日：
            <input
                type="date"
                name="birthday"
            >
        </p>

        <p>
            LINE User ID：
            <input
                type="text"
                name="line_user_id"
            >
        </p>

        <p>
            來店次數：
            <input
                type="number"
                name="visit_count"
                value="0"
            >
        </p>

        <p>
            累積消費：
            <input
                type="number"
                name="total_amount"
                value="0"
            >
        </p>

        <p>
            偏好商品：
            <input
                type="text"
                name="favorite_product"
            >
        </p>

        <p>
            會員照片：
            <input
                type="file"
                name="face_image"
                accept=".jpg,.jpeg,.png"
                required
            >
        </p>

        <p>
            是否 VIP：
            <select name="vip">
                <option value="0">
                    一般會員
                </option>

                <option value="1">
                    VIP會員
                </option>
            </select>
        </p>

        <button type="submit">
            新增會員
        </button>
    </form>

    <p>
        <a href="/member">
            回會員列表
        </a>
    </p>
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

    cursor.execute("""
        SELECT member_id, name, phone, birthday, vip, member_level,
               visit_count, line_user_id, total_amount,
               favorite_product, face_image, registration_source
        FROM members
        WHERE member_id = %s
    """, (member_id,))

    target_member = cursor.fetchone()

    if target_member is None:
        cursor.close()
        conn.close()
        return "找不到會員"

    if request.method == "POST":
         vip = request.form.get("vip") == "1"
         member_level = "vip" if vip else "normal"
       
         sql = """
        UPDATE members
        SET name = %s,
            phone = %s,
            birthday = %s,
            vip = %s,
            member_level = %s,
            visit_count = %s,
            line_user_id = %s,
            total_amount = %s,
            favorite_product = %s,
            face_image = %s
        WHERE member_id = %s
        """

         data = (
            request.form.get("name"),
            request.form.get("phone"),
            request.form.get("birthday") or None,
            vip,
            member_level,
            int(request.form.get("visit_count") or 0),
            request.form.get("line_user_id"),
            int(request.form.get("total_amount") or 0),
            request.form.get("favorite_product"),
            request.form.get("face_image"),
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

    <form method="POST" enctype="multipart/form-data">
        <p>會員編號：{target_member['member_id']}</p>
        <p>姓名：<input type="text" name="name" value="{target_member['name'] or ''}"></p>
        <p>電話：<input type="text" name="phone" value="{target_member['phone'] or ''}"></p>
        <p>生日：<input type="date" name="birthday" value="{target_member['birthday'] or ''}"></p>
        <p>LINE User ID：<input type="text" name="line_user_id" value="{target_member['line_user_id'] or ''}"></p>
        <p>來店次數：<input type="number" name="visit_count" value="{target_member['visit_count'] or 0}"></p>
        <p>累積消費：<input type="number" name="total_amount" value="{target_member['total_amount'] or 0}"></p>
        <p>偏好商品：<input type="text" name="favorite_product" value="{target_member['favorite_product'] or ''}"></p>
        <p>人臉圖片路徑：<input type="text" name="face_image" value="{target_member['face_image'] or ''}"></p>
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