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
    convert_visitor_to_member,
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
    find_matching_visitor,
    is_path_within_directory,
    remove_member_from_face_cache,
    sync_converted_visitor_cache,
    validate_member_face_image,
    reload_member_faces,
    reload_visitor_faces,
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

    if normalized_path.startswith(
        ("https://", "http://")
    ):
        return normalized_path

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
                COALESCE(
                    NULLIF(face_image, ''),
                    (
                        SELECT fi.image_path
                        FROM face_images AS fi
                        WHERE fi.member_id = members.member_id
                        ORDER BY fi.face_id DESC
                        LIMIT 1
                    )
                ) AS face_image,
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
                COALESCE(
                    latest_log.visit_time,
                    latest_log.recognized_at,
                    m.last_visit_time
                ) AS last_visit_time,
                CASE
                    WHEN latest_log.log_id IS NULL THEN NULL
                    WHEN COALESCE(latest_log.stay_seconds, 0) > 0
                        THEN latest_log.stay_seconds
                    ELSE GREATEST(
                        TIMESTAMPDIFF(
                            SECOND,
                            COALESCE(
                                latest_log.visit_time,
                                latest_log.recognized_at
                            ),
                            COALESCE(
                                latest_log.leave_time,
                                latest_log.last_seen_at,
                                latest_log.visit_time,
                                latest_log.recognized_at
                            )
                        ),
                        0
                    )
                END AS latest_stay_seconds,
                m.line_user_id,
                m.total_amount,
                m.favorite_product,
                COALESCE(
                    NULLIF(m.face_image, ''),
                    (
                        SELECT fi.image_path
                        FROM face_images AS fi
                        WHERE fi.member_id = m.member_id
                        ORDER BY fi.face_id DESC
                        LIMIT 1
                    )
                ) AS face_image,
                m.registration_source,
                m.created_at,
                m.updated_at
            FROM members AS m
            LEFT JOIN recognition_logs AS latest_log
                ON latest_log.log_id = (
                    SELECT rl.log_id
                    FROM recognition_logs AS rl
                    WHERE rl.member_id = m.member_id
                      AND rl.subject_type = 'member'
                    ORDER BY
                        COALESCE(rl.visit_time, rl.recognized_at) DESC,
                        rl.log_id DESC
                    LIMIT 1
                )
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

            # 7. 後台與 LINE 註冊共用相同的散客轉會員規則。
            name = request.form.get("name")
            line_user_id = request.form.get("line_user_id")
            visitor_match = find_matching_visitor(encoding_data)

            if visitor_match.get("matched"):
                convert_result = convert_visitor_to_member(
                    visitor_id=visitor_match["visitor_id"],
                    name=name,
                    phone=request.form.get("phone"),
                    birthday=request.form.get("birthday") or None,
                    vip=vip,
                    member_level=member_level,
                    line_user_id=line_user_id,
                    registration_source="backend_visitor_conversion",
                    registration_image_path=saved_image_path,
                    registration_encoding=encoding_data,
                    updated_by="backend",
                    total_amount=request.form.get("total_amount") or 0,
                    favorite_product=request.form.get(
                        "favorite_product"
                    ),
                )
                member_id = convert_result["member_id"]

                reload_member_faces()
                reload_visitor_faces()
                sync_converted_visitor_cache(
                    visitor_id=visitor_match["visitor_id"],
                    member_id=member_id,
                    registration_encoding=encoding_data,
                    registration_image_path=saved_image_path,
                )

                from routes.camera import convert_visitor_active_visit
                convert_visitor_active_visit(
                    visitor_id=visitor_match["visitor_id"],
                    member_id=member_id,
                    name=name,
                    vip=vip,
                    member_level=member_level,
                    line_user_id=line_user_id,
                    converted_active_log_id=convert_result.get(
                        "converted_active_log_id"
                    ),
                )
            else:
                register_member_with_face(
                    name=name,
                    phone=request.form.get("phone"),
                    birthday=request.form.get("birthday") or None,
                    vip=vip,
                    member_level=member_level,
                    total_visit_count=0,
                    last_visit_time=None,
                    total_visit_time=0,
                    updated_by="backend",
                    line_user_id=line_user_id,
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

        cursor.execute(
            "SELECT image_path FROM face_images WHERE member_id = %s",
            (member_id,)
        )
        member_image_paths = [
            row[0]
            for row in cursor.fetchall()
            if row and row[0]
        ]

        cursor.execute("DELETE FROM vip_notifications WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM recognition_logs WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM face_images WHERE member_id = %s", (member_id,))
        cursor.execute("DELETE FROM members WHERE member_id = %s", (member_id,))

        conn.commit()        
        remove_member_from_face_cache(member_id)
        reload_member_faces()
        reload_visitor_faces()

        for image_path in member_image_paths:
            if not is_path_within_directory(
                image_path,
                MEMBER_IMAGE_DIR
            ):
                continue

            try:
                if os.path.isfile(image_path):
                    os.remove(image_path)
            except OSError as image_error:
                print(
                    "刪除會員照片失敗："
                    f"path={image_path}, error={image_error}"
                )

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


@member_bp.route(
    "/member/edit/<int:member_id>",
    methods=["GET", "POST"]
)
def edit_member(member_id):
    conn = None
    cursor = None
    new_image_path = None
    old_image_path = None
    database_committed = False

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
                line_user_id,
                total_amount,
                favorite_product,
                face_image,
                registration_source
            FROM members
            WHERE member_id = %s
        """, (member_id,))

        target_member = cursor.fetchone()

        if target_member is None:
            return "找不到會員", 404

        # =============================
        # POST：儲存會員修改
        # =============================
        if request.method == "POST":
            image_file = request.files.get("face_image")

            has_new_image = bool(
                image_file
                and image_file.filename
            )

            encoding_json = None

            # -----------------------------
            # 1. 取得表單欄位
            # -----------------------------
            name = (request.form.get("name") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            birthday = request.form.get("birthday") or None
            line_user_id = (
                request.form.get("line_user_id") or ""
            ).strip() or None

            favorite_product = (
                request.form.get("favorite_product") or ""
            ).strip() or None

            requested_vip = (
                request.form.get("vip") == "1"
            )

            try:
                new_total_amount = float(
                    request.form.get("total_amount") or 0
                )
            except (TypeError, ValueError):
                return redirect(url_for(
                    "member.member_detail",
                    member_id=member_id,
                    error="累積消費金額格式錯誤。"
                ))

            if new_total_amount < 0:
                return redirect(url_for(
                    "member.member_detail",
                    member_id=member_id,
                    error="累積消費金額不可小於 0。"
                ))

            # -----------------------------
            # 2. 判斷是否自動升級 VIP
            # -----------------------------
            was_normal = not bool(
                target_member.get("vip")
            )

            upgraded_to_vip = (
                was_normal
                and new_total_amount
                >= VIP_UPGRADE_THRESHOLD
            )

            # 一般會員消費達門檻時，自動升級。
            # 若原本已是 VIP，仍允許店員手動調整。
            final_vip = (
                True
                if upgraded_to_vip
                else requested_vip
            )

            member_level = (
                "vip"
                if final_vip
                else "normal"
            )

            # -----------------------------
            # 3. 有上傳新照片才處理照片
            # -----------------------------
            if has_new_image:
                if not allowed_image_file(
                    image_file.filename
                ):
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "照片格式不支援，"
                            "請上傳 JPG、JPEG 或 PNG 檔案。"
                        )
                    ))

                if (
                    image_file.mimetype
                    not in ALLOWED_IMAGE_MIME_TYPES
                ):
                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "照片格式不支援，"
                            "請上傳 JPG、JPEG 或 PNG 檔案。"
                        )
                    ))

                original_filename = secure_filename(
                    image_file.filename
                )

                extension = (
                    original_filename
                    .rsplit(".", 1)[1]
                    .lower()
                )

                new_filename = (
                    f"member_{uuid.uuid4().hex}."
                    f"{extension}"
                )

                new_image_path = os.path.join(
                    MEMBER_IMAGE_DIR,
                    new_filename
                )

                image_file.save(new_image_path)

                # 驗證照片是否只有一張人臉
                face_check_result = (
                    validate_member_face_image(
                        new_image_path
                    )
                )

                if not face_check_result.get("success"):
                    if os.path.exists(new_image_path):
                        os.remove(new_image_path)

                    new_image_path = None

                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=face_check_result.get(
                            "message",
                            (
                                "會員照片驗證失敗，"
                                "原照片已保留。"
                            )
                        )
                    ))

                encoding_data = face_check_result.get(
                    "encoding"
                )

                if encoding_data is None:
                    if os.path.exists(new_image_path):
                        os.remove(new_image_path)

                    new_image_path = None

                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "新照片無法產生人臉特徵，"
                            "原照片已保留。"
                        )
                    ))

                encoding_json = normalize_encoding_data(
                    encoding_data
                )

                # 排除會員自己原本的人臉，
                # 只檢查是否與其他會員重複。
                duplicate_result = check_duplicate_face(
                    encoding_data,
                    exclude_member_id=member_id
                )

                if duplicate_result.get("is_duplicate"):
                    if os.path.exists(new_image_path):
                        os.remove(new_image_path)

                    new_image_path = None

                    duplicate_name = (
                        duplicate_result.get("name")
                        or "其他會員"
                    )

                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            f"此人臉已屬於"
                            f"{duplicate_name}，"
                            "請確認照片後再重新上傳。"
                        )
                    ))

            # -----------------------------
            # 4. 更新會員基本資料
            # -----------------------------
            cursor.execute("""
                UPDATE members
                SET
                    name = %s,
                    phone = %s,
                    birthday = %s,
                    vip = %s,
                    member_level = %s,
                    line_user_id = %s,
                    total_amount = %s,
                    favorite_product = %s,
                    updated_by = %s
                WHERE member_id = %s
            """, (
                name,
                phone,
                birthday,
                final_vip,
                member_level,
                line_user_id,
                new_total_amount,
                favorite_product,
                (
                    "vip_auto_upgrade"
                    if upgraded_to_vip
                    else "backend"
                ),
                member_id
            ))

            # -----------------------------
            # 5. 有新照片才更新 face_images
            # -----------------------------
            if has_new_image:
                cursor.execute("""
                    SELECT
                        face_id,
                        image_path
                    FROM face_images
                    WHERE member_id = %s
                    ORDER BY face_id DESC
                    LIMIT 1
                    FOR UPDATE
                """, (member_id,))

                current_face = cursor.fetchone()

                if current_face:
                    old_image_path = (
                        current_face.get("image_path")
                    )

                    cursor.execute("""
                        UPDATE face_images
                        SET
                            image_path = %s,
                            encoding_data = %s
                        WHERE face_id = %s
                    """, (
                        new_image_path,
                        encoding_json,
                        current_face["face_id"]
                    ))

                else:
                    old_image_path = (
                        target_member.get("face_image")
                    )

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

            # -----------------------------
            # 6. 正式提交資料庫
            # -----------------------------
            conn.commit()
            database_committed = True

            # -----------------------------
            # 7. 更新 AI 人臉快取
            # -----------------------------
            if has_new_image:
                try:
                    loaded_members = reload_member_faces()

                    # 散客資料未修改，但一起重新整理，
                    # 避免散客轉會員後殘留舊快取。
                    reload_visitor_faces()

                except Exception as reload_error:
                    print(
                        "會員人臉資料重新載入失敗：",
                        reload_error
                    )

                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "會員資料與照片已更新，"
                            "但人臉辨識快取重新載入失敗。"
                        )
                    ))

                member_loaded = any(
                    member_data.get("member_id")
                    == member_id
                    for member_data in loaded_members
                )

                if not member_loaded:
                    print(
                        "人臉快取找不到會員：",
                        member_id
                    )

                    return redirect(url_for(
                        "member.member_detail",
                        member_id=member_id,
                        error=(
                            "會員資料與照片已更新，"
                            "但攝影機尚未載入新照片。"
                        )
                    ))

            else:
                # 沒換照片時只刷新該會員的
                # 姓名、VIP、消費等快取資料。
                refreshed = refresh_member(member_id)

                if not refreshed:
                    reload_member_faces()

            # -----------------------------
            # 8. 資料成功後刪除舊照片
            # -----------------------------
            if (
                has_new_image
                and old_image_path
                and old_image_path != new_image_path
                and is_path_within_directory(
                    old_image_path,
                    MEMBER_IMAGE_DIR
                )
            ):
                try:
                    if os.path.isfile(old_image_path):
                        os.remove(old_image_path)

                except OSError as image_error:
                    print(
                        "刪除會員舊照片失敗："
                        f"path={old_image_path}, "
                        f"error={image_error}"
                    )

            # -----------------------------
            # 9. 自動升級 VIP 時發送通知
            # -----------------------------
            if upgraded_to_vip:
                try:
                    notify_vip_upgrade({
                        "member_id": member_id,
                        "name": (
                            name
                            or target_member.get("name")
                        ),
                        "line_user_id": line_user_id,
                    })

                except Exception as notify_error:
                    print(
                        "VIP 升級通知失敗：",
                        notify_error
                    )

            return redirect(url_for(
                "member.member_detail",
                member_id=member_id,
                saved=1
            ))

    except Exception as e:
        if (
            conn is not None
            and not database_committed
        ):
            conn.rollback()

        # 資料庫尚未成功時，
        # 刪除這次新上傳但未使用的照片。
        if (
            new_image_path
            and not database_committed
            and os.path.exists(new_image_path)
        ):
            try:
                os.remove(new_image_path)
            except OSError:
                pass

        print(
            "修改會員失敗："
            f"{type(e).__name__}: {e}"
        )

        return redirect(url_for(
            "member.member_detail",
            member_id=member_id,
            error=(
                "會員資料儲存失敗，"
                "原照片已保留，請稍後再試。"
            )
        ))

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()

    # =============================
    # GET：顯示修改表單
    # =============================
    vip_selected = (
        "selected"
        if target_member["vip"]
        else ""
    )

    normal_selected = (
        ""
        if target_member["vip"]
        else "selected"
    )

    birthday_value = (
        target_member["birthday"]
        or ""
    )

    return f"""
    <h1>修改會員</h1>

    <form method="POST" enctype="multipart/form-data">
        <p>
            會員編號：{target_member['member_id']}
        </p>

        <p>
            姓名：
            <input
                type="text"
                name="name"
                value="{target_member['name'] or ''}"
                required
            >
        </p>

        <p>
            電話：
            <input
                type="text"
                name="phone"
                value="{target_member['phone'] or ''}"
            >
        </p>

        <p>
            生日：
            <input
                type="date"
                name="birthday"
                value="{birthday_value}"
            >
        </p>

        <p>
            LINE User ID：
            <input
                type="text"
                name="line_user_id"
                value="{target_member['line_user_id'] or ''}"
            >
        </p>

        <p>
            累積到店次數（系統自動計算）：
            {target_member['total_visit_count'] or 0}
        </p>

        <p>
            累積消費：
            <input
                type="number"
                name="total_amount"
                min="0"
                step="1"
                value="{target_member['total_amount'] or 0}"
            >
        </p>

        <p>
            偏好商品：
            <input
                type="text"
                name="favorite_product"
                value="{target_member['favorite_product'] or ''}"
            >
        </p>

        <p>
            目前人臉圖片：
            {target_member['face_image'] or '尚未設定'}
        </p>

        <p>
            重新上傳會員照片：
            <input
                type="file"
                name="face_image"
                accept=".jpg,.jpeg,.png"
            >
        </p>

        <p>
            未選擇新照片時，會保留目前照片。
        </p>

        <p>
            是否 VIP：
            <select name="vip">
                <option
                    value="0"
                    {normal_selected}
                >
                    一般會員
                </option>

                <option
                    value="1"
                    {vip_selected}
                >
                    VIP會員
                </option>
            </select>
        </p>

        <button type="submit">
            儲存修改
        </button>
    </form>

    <p>
        <a href="/member">
            回會員列表
        </a>
    </p>
    """
