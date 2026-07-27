import os
import uuid

from flask import (
    Blueprint,
    request,
    redirect,
    jsonify,
    render_template,
    url_for,
    send_from_directory,
)
from werkzeug.utils import secure_filename

from database.db import (
    get_connection,
    normalize_encoding_data,
    save_recognition_log,
    register_member_with_face,
)
from linebot_service.notify import notify_vip_upgrade

# 累積消費達到這個門檻，自動升級 VIP 並推播通知。
# 跟 routes/line.py 的 VIP_UPGRADE_THRESHOLD 是同一個門檻值，
# 兩邊各自獨立觸發（這裡是店員編輯當下、那邊是排程批次檢查），
# 之後如果要調整門檻，兩個檔案都要一起改。
VIP_UPGRADE_THRESHOLD = 10000

UPLOAD_FOLDER = os.path.join(
    "static",
    "member_images"
)

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )

# 請依照你專案實際資料夾位置調整
from services.face_service import (
    check_duplicate_face,
    validate_member_face_image,
    reload_member_faces,
    refresh_member,
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

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png"
}

def allowed_image_file(filename):
    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_IMAGE_EXTENSIONS


def _safe_member_image_url(image_path):
    if not image_path:
        return None

    normalized_path = str(image_path).replace("\\", "/")
    static_marker = "static/"
    member_image_marker = "member_images/"

    if normalized_path.startswith(static_marker):
        return url_for(
            "static",
            filename=normalized_path[len(static_marker):]
        )

    if static_marker in normalized_path:
        return url_for(
            "static",
            filename=normalized_path.split(static_marker, 1)[1]
        )

    if os.path.isabs(str(image_path)):
        if member_image_marker in normalized_path:
            filename = normalized_path.rsplit(member_image_marker, 1)[1]
            return url_for("member.member_image", filename=filename)

        return None

    if member_image_marker in normalized_path:
        filename = normalized_path.rsplit(member_image_marker, 1)[1]
    else:
        filename = normalized_path

    return url_for("member.member_image", filename=filename)


def _get_member_detail(member_id):
    conn = None
    cursor = None

    try:
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
            WHERE member_id = %s
        """, (member_id,))

        member = cursor.fetchone()

        if member is None:
            return None

        member["display_face_image"] = _safe_member_image_url(
            member.get("face_image")
        )

        return member


    except Exception as e:
        print("取得會員詳細資料失敗：", e)
        return {}

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


def _get_member_visit_records(member_id):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT log_id, visit_time, recognized_at, last_seen_at,
                   leave_time, stay_seconds, visit_status
            FROM recognition_logs
            WHERE member_id = %s
            ORDER BY visit_time DESC, recognized_at DESC, log_id DESC
        """, (member_id,))

        return cursor.fetchall() or []

    except Exception as e:
        print("取得會員到店歷史失敗：", e)
        return []

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()

@member_bp.route("/member")
def member():
    keyword = request.args.get("keyword", "").strip()

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
            SELECT
                m.member_id,
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
                m.created_at,
                m.updated_at,
                latest_visit.last_visit_time
            FROM members AS m
            LEFT JOIN (
                SELECT
                    member_id,
                    MAX(
                        COALESCE(visit_time, recognized_at)
                    ) AS last_visit_time
                FROM recognition_logs
                WHERE member_id IS NOT NULL
                  AND subject_type = 'member'
                GROUP BY member_id
            ) AS latest_visit
                ON latest_visit.member_id = m.member_id
        """

        params = ()

        if keyword:
            search_pattern = f"%{keyword}%"

            sql += """
                WHERE m.name LIKE %s
                   OR m.phone LIKE %s
                   OR m.line_user_id LIKE %s
            """

            params = (
                search_pattern,
                search_pattern,
                search_pattern
            )

        sql += " ORDER BY m.member_id ASC"

        cursor.execute(sql, params)
        members = cursor.fetchall() or []

        for member_data in members:
            member_data["display_face_image"] = (
                _safe_member_image_url(
                    member_data.get("face_image")
                )
            )

        return render_template(
            "member.html",
            members=members,
            keyword=keyword
        )

    except Exception as e:
        print("取得會員列表失敗：", e)

        return render_template(
            "member.html",
            members=[],
            keyword=keyword,
            load_error="會員資料載入失敗"
        ), 500

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


@member_bp.route("/member_images/<path:filename>")
def member_image(filename):
    return send_from_directory(MEMBER_IMAGE_DIR, filename)


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

   

@member_bp.route("/member/<int:member_id>")
def member_detail(member_id):
    member = _get_member_detail(member_id)
    records = _get_member_visit_records(member_id)

    return render_template(
        "member_detail.html",
        member=member,
        records=records
    )


@member_bp.route("/member/add", methods=["GET", "POST"])
def add_member_page():
    if request.method == "POST":
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
            original_filename = secure_filename(image_file.filename)
            extension = original_filename.rsplit(".", 1)[1].lower()
            new_filename = f"member_{uuid.uuid4().hex}.{extension}"

            saved_image_path = os.path.join(
                MEMBER_IMAGE_DIR,
                new_filename
            )

            # 4. 把照片存到 member_images
            image_file.save(saved_image_path)

            # 5. 驗證照片並取得 128 維人臉 encoding
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

            encoding_data = face_check_result.get("encoding")

            if encoding_data is None:
                if os.path.exists(saved_image_path):
                    os.remove(saved_image_path)

                return "會員照片沒有產生人臉特徵資料", 400

            # 6. 整理會員欄位
            vip = request.form.get("vip") == "1"
            member_level = "vip" if vip else "normal"

            # 7. members 與 face_images 使用同一筆 transaction
            register_member_with_face(
                name=request.form.get("name"),
                phone=request.form.get("phone"),
                birthday=request.form.get("birthday") or None,
                vip=vip,
                member_level=member_level,
                # 累積到店數只能由離店流程更新，不能由管理頁手動輸入。
                total_visit_count=0,
                last_visit_time=None,
                total_visit_time=0,
                updated_by="backend",
                line_user_id=request.form.get("line_user_id"),
                total_amount=request.form.get("total_amount") or 0,
                favorite_product=request.form.get(
                    "favorite_product"
                ),
                face_image=saved_image_path,
                registration_source="backend",
                image_path=saved_image_path,
                encoding_data=encoding_data
            )

            # 8. 資料庫成功後，重新載入 AI 會員人臉名單
            reload_member_faces()

            return redirect("/member")

        except Exception as e:
            # register_member_with_face 會自行 rollback；
            # 這裡只清除已存到硬碟的照片。
            if (
                saved_image_path
                and os.path.exists(saved_image_path)
            ):
                os.remove(saved_image_path)

            print("新增會員失敗：", e)
            return f"新增會員失敗：{e}", 500

    # GET：顯示新增會員表單
    return """
    <h1>新增會員</h1>

    <form method="POST" enctype="multipart/form-data">
        <p>
            姓名：
            <input type="text" name="name" required>
        </p>

        <p>
            電話：
            <input type="text" name="phone">
        </p>

        <p>
            生日：
            <input type="date" name="birthday">
        </p>

        <p>
            LINE User ID：
            <input type="text" name="line_user_id">
        </p>

        <p>
            累積消費：
            <input type="number" name="total_amount" value="0">
        </p>

        <p>
            偏好商品：
            <input type="text" name="favorite_product">
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
                <option value="0">一般會員</option>
                <option value="1">VIP會員</option>
            </select>
        </p>

        <button type="submit">新增會員</button>
    </form>

    <p><a href="/member">回會員列表</a></p>
    """


@member_bp.route("/member/delete/<int:member_id>", methods=["POST"])
def delete_member(member_id):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM vip_notifications WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM recognition_logs WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM face_images WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM members WHERE member_id = %s", (member_id,))

        conn.commit()

        return redirect("/member")

    except Exception as e:
        print("delete member failed:", e)

        if conn is not None:
            conn.rollback()

        return redirect(url_for("member.member", delete_error=1))

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


@member_bp.route("/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    conn = None
    cursor = None
    new_image_path = None
    database_committed = False

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT member_id, name, phone, birthday, vip, member_level,
                   total_visit_count, line_user_id, total_amount,
                   favorite_product, face_image, registration_source
            FROM members
            WHERE member_id = %s
        """, (member_id,))

        target_member = cursor.fetchone()

        if target_member is None:
            return "找不到會員", 404

        if request.method == "POST":
            image_file = request.files.get("face_image")
            has_new_image = bool(
                image_file
                and image_file.filename
            )
            encoding_json = None

            if has_new_image:
                if not allowed_image_file(image_file.filename):
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error="照片格式不支援，請上傳 JPG、JPEG 或 PNG 檔案。"
                    ))

                if image_file.mimetype not in ALLOWED_IMAGE_MIME_TYPES:
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error="照片格式不支援，請上傳 JPG、JPEG 或 PNG 檔案。"
                    ))

                extension = (
                    image_file.filename.rsplit(".", 1)[1].lower()
                )
                new_filename = (
                    f"member_{uuid.uuid4().hex}.{extension}"
                )
                new_image_path = os.path.join(
                    MEMBER_IMAGE_DIR,
                    new_filename
                )
                image_file.save(new_image_path)

                face_check_result = validate_member_face_image(
                    new_image_path
                )

                if not face_check_result.get("success"):
                    os.remove(new_image_path)
                    new_image_path = None
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=face_check_result.get(
                            "message",
                            "會員照片驗證失敗，原照片已保留。"
                        )
                    ))

                encoding_data = face_check_result.get("encoding")
                encoding_json = normalize_encoding_data(
                    encoding_data
                )

                duplicate_result = check_duplicate_face(
                    encoding_data,
                    exclude_member_id=member_id
                )

                if duplicate_result.get("is_duplicate"):
                    os.remove(new_image_path)
                    new_image_path = None
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "此人臉已屬於其他會員，"
                            "請確認照片後再重新上傳。"
                        )
                    ))

            vip = request.form.get("vip") == "1"
            member_level = "vip" if vip else "normal"

            cursor.execute("""
                UPDATE members
                SET name = %s,
                    phone = %s,
                    birthday = %s,
                    vip = %s,
                    member_level = %s,
                    favorite_product = %s,
                    updated_by = 'backend'
                WHERE member_id = %s
            """, (
                request.form.get("name"),
                request.form.get("phone"),
                request.form.get("birthday") or None,
                vip,
                member_level,
                request.form.get("favorite_product"),
                member_id
            ))

            if has_new_image:
                cursor.execute("""
                    SELECT face_id
                    FROM face_images
                    WHERE member_id = %s
                    ORDER BY face_id DESC
                    LIMIT 1
                    FOR UPDATE
                """, (member_id,))
                current_face = cursor.fetchone()

                if current_face:
                    cursor.execute("""
                        UPDATE face_images
                        SET image_path = %s,
                            encoding_data = %s
                        WHERE face_id = %s
                    """, (
                        new_image_path,
                        encoding_json,
                        current_face["face_id"]
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO face_images (
                            member_id,
                            image_path,
                            encoding_data
                        )
                        VALUES (%s, %s, %s)
                    """, (
                        member_id,
                        new_image_path,
                        encoding_json
                    ))

                cursor.execute("""
                    UPDATE members
                    SET face_image = %s
                    WHERE member_id = %s
                """, (
                    new_image_path,
                    member_id
                ))

            # 消費金額跨過門檻時自動升級 VIP。跟 routes/line.py 的
            # POST /line/cron/vip-check（排程批次檢查）是各自獨立的觸發點，
            # 這裡是店員手動編輯當下就觸發，兩邊門檻值要保持一致。
            was_normal = not bool(target_member.get("vip"))

            try:
                new_total_amount = float(
                    target_member.get("total_amount") or 0
                )
            except (TypeError, ValueError):
                new_total_amount = 0

            upgraded_to_vip = (
                was_normal
                and new_total_amount >= VIP_UPGRADE_THRESHOLD
            )

            if upgraded_to_vip:
                cursor.execute(
                    "UPDATE members SET vip = TRUE, member_level = 'vip', "
                    "updated_by = 'vip_auto_upgrade' WHERE member_id = %s",
                    (member_id,)
                )

            conn.commit()
            database_committed = True

            if has_new_image:
                try:
                    loaded_members = reload_member_faces()
                except Exception as reload_error:
                    print("會員人臉資料重新載入失敗：", reload_error)
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "會員照片已更新，但人臉辨識資料重新載入失敗。"
                            "請至 Camera 頁重新載入人臉資料。"
                        )
                    ))

                if not any(
                    member_data.get("member_id") == member_id
                    for member_data in loaded_members
                ):
                    print(
                        "會員人臉資料重新載入後找不到會員：",
                        member_id
                    )
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "會員照片已更新，但人臉辨識資料尚未載入。"
                            "請至 Camera 頁重新載入人臉資料。"
                        )
                    ))
            else:
                refresh_member(member_id)

            if upgraded_to_vip:
                try:
                    notify_vip_upgrade({
                        "member_id": member_id,
                        "name": (
                            request.form.get("name")
                            or target_member.get("name")
                        ),
                        "line_user_id": (
                            target_member.get("line_user_id")
                        ),
                    })
                except Exception as notify_error:
                    print("VIP 升級通知失敗：", notify_error)

            return redirect(url_for(
                "member.member_detail",
                member_id=member_id,
                saved=1
            ))

    except Exception as e:
        if conn is not None and not database_committed:
            conn.rollback()

        if (
            new_image_path
            and not database_committed
            and os.path.exists(new_image_path)
        ):
            os.remove(new_image_path)

        print("修改會員失敗：", e)

        return redirect(url_for(
            "member.member_detail",
            member_id=member_id,
            error=(
                "會員資料儲存失敗，原照片已保留，"
                "請稍後再試。"
            )
        ))

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
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
        <p>累積到店次數（系統自動計算）：{target_member['total_visit_count'] or 0}</p>
        <p>累積消費：<input type="number" name="total_amount" value="{target_member['total_amount'] or 0}"></p>
        <p>偏好商品：<input type="text" name="favorite_product" value="{target_member['favorite_product'] or ''}"></p>
        <p>人臉圖片：{target_member['face_image'] or '尚未設定'}</p>
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
