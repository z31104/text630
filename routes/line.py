import json
import os
import uuid
from datetime import datetime, timedelta
import traceback
from routes.llm_service import ask_llm

import requests
from flask import Blueprint, request, abort, jsonify, redirect
from markupsafe import escape

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FollowEvent, MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, URIAction,
)

from database.db import (
    get_connection,
    register_member_with_face,
    convert_visitor_to_member,
    draw_lottery_for_member,
    get_member_coupons,
    get_member_non_coupon_prizes,
    issue_registration_welcome_coupon,
    get_member_prize,
    get_lottery_prize_display_name,
    REDEMPTION_BASE_URL,
    get_latest_unconverted_visitor,
    get_redemption_by_token,
    redeem_member_prize,
)
from linebot_service.notify import (
    push_message,
    notify_lottery_result,
    notify_vip_upgrade,
    notify_vip_recognition,
)
from services.face_service import (
    validate_member_face_image,
    check_duplicate_face,
    find_matching_visitor,
    reload_member_faces,
    reload_visitor_faces,
    sync_converted_visitor_cache,
    MEMBER_IMAGE_DIR,
)
from routes.home import prepare_member_coupon_rows
from services.image_storage import (
    delete_member_image,
    persist_member_image,
)

ALLOWED_FACE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_FACE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}

line_bp = Blueprint("line", __name__)


def _cleanup_registration_image(local_path, stored_path=None):
    if stored_path:
        try:
            delete_member_image(
                stored_path,
                local_roots=(MEMBER_IMAGE_DIR,),
            )
        except Exception as cleanup_error:
            print("清除會員註冊照片失敗：", cleanup_error)

    if (
        local_path
        and local_path != stored_path
        and os.path.isfile(local_path)
    ):
        os.remove(local_path)

REGISTER_KEYWORDS = {"註冊", "會員", "加入會員", "register"}

# 顧客用 LINE 官方帳號
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_ENABLED = bool(LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET)

if LINE_ENABLED:
    from linebot_service.notify import notify_new_friend

    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
else:
    line_bot_api = None
    handler = None
    print("警告：未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，LINE Bot 進入測試模式")

# LIFF App ID，前端 register.js 用來呼叫 liff.init()
LIFF_ID = os.getenv("LIFF_ID", "")

# 「我的會員／優惠券」頁用的第二個 LIFF App ID，前端 coupons.js 用來呼叫 liff.init()
# 跟 LIFF_ID 共用同一個 LINE Login channel，所以 ID Token 的 aud 驗證不受影響
LIFF_ID_COUPONS = os.getenv("LIFF_ID_COUPONS", "")

# LIFF ID 格式固定是「{LINE Login channel id}-{liff app id}」，
# 驗證 ID Token 的 aud/client_id 要用前半段的 channel id。
LIFF_CHANNEL_ID = LIFF_ID.split("-")[0] if LIFF_ID else ""
LIFF_COUPONS_CHANNEL_ID = (
    LIFF_ID_COUPONS.split("-")[0]
    if LIFF_ID_COUPONS
    else ""
)

LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
LINE_PROFILE_URL = "https://api.line.me/v2/profile"

# 累積消費金額達到這個門檻，自動升級 VIP 並推播通知
VIP_UPGRADE_THRESHOLD = 10000

# 保護 /line/cron/vip-check 用的密鑰，Cloud Scheduler 呼叫時要帶在
# X-Cron-Secret header 裡；本機沒設定時這支 API 直接回 403，避免忘記
# 設定密鑰卻讓外部任何人都能觸發批次升級。
CRON_SECRET = os.getenv("CRON_SECRET", "")

# 店員用 LINE 官方帳號，用來接收 VIP 到店通知
STAFF_LINE_CHANNEL_ACCESS_TOKEN = os.getenv("STAFF_LINE_CHANNEL_ACCESS_TOKEN")
STAFF_LINE_CHANNEL_SECRET = os.getenv("STAFF_LINE_CHANNEL_SECRET")
STAFF_LINE_ENABLED = bool(STAFF_LINE_CHANNEL_ACCESS_TOKEN and STAFF_LINE_CHANNEL_SECRET)

if STAFF_LINE_ENABLED:
    staff_line_bot_api = LineBotApi(STAFF_LINE_CHANNEL_ACCESS_TOKEN)
    staff_handler = WebhookHandler(STAFF_LINE_CHANNEL_SECRET)
else:
    staff_line_bot_api = None
    staff_handler = None
    print("警告：未設定 STAFF_LINE_CHANNEL_ACCESS_TOKEN / STAFF_LINE_CHANNEL_SECRET，店員 LINE Bot 進入測試模式")


def get_registration_link(line_user_id):
    if LIFF_ID:
        return f"https://liff.line.me/{LIFF_ID}"

    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = request.url_root.rstrip("/")
        if base_url.startswith("http://"):
            # ngrok 對外一定是 https，但轉送到本機 Flask 時是用 http，
            # 這裡把 scheme 校正成 https，否則 LINE 會拒絕整則按鈕訊息
            base_url = "https://" + base_url[len("http://"):]
    return f"{base_url}/register?line_user_id={line_user_id}"


def build_register_message(line_user_id):
    link = get_registration_link(line_user_id)
    return TemplateSendMessage(
        alt_text="立即完成會員註冊，領取新會員禮！",
        template=ButtonsTemplate(
            title="歡迎加入！",
            text="完成會員註冊即可領取新會員禮與抽獎機會",
            actions=[
                URIAction(label="立即註冊會員", uri=link)
            ]
        )
    )


@line_bp.route("/line")
def line_index():
    if not LINE_ENABLED:
        return """
        <h1>LINE Bot - 測試模式</h1>
        <p>未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，目前為測試模式</p>
        """
    return """
    <h1>LINE Bot - 正式模式</h1>
    <p>已偵測到 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET，LINE Bot 已啟動</p>
    """


@line_bp.route("/line/config")
def line_config():
    """提供前端 register.js / coupons.js 需要的公開設定值（LIFF ID）。"""
    return jsonify({"liff_id": LIFF_ID, "liff_id_coupons": LIFF_ID_COUPONS})


@line_bp.route("/line/member")
@line_bp.route("/my-member")
@line_bp.route("/member-area")
def member_portal():
    """LINE Rich Menu 的穩定會員專區入口。"""
    if LIFF_ID_COUPONS:
        return redirect(
            f"https://liff.line.me/{LIFF_ID_COUPONS}",
            code=302,
        )

    return redirect("/coupons", code=302)


@line_bp.route("/line/callback", methods=["POST"])
def callback():
    if not LINE_ENABLED:
        return "OK (test mode)"

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


if LINE_ENABLED:
    @handler.add(FollowEvent)
    def handle_follow(event):
        user_id = event.source.user_id

        # 加好友的瞬間，此時對方應為非會員，先推播一次通用歡迎訊息，
        # 再接著推播一則帶有註冊連結的按鈕訊息
        notify_new_friend(user_id)
        line_bot_api.push_message(user_id, build_register_message(user_id))

    @handler.add(MessageEvent, message=TextMessage)
    def handle_message(event):
        user_id = event.source.user_id
        text = event.message.text.strip()

        print("收到訊息:", text)
        print("使用者 userId:", user_id)

        # 註冊關鍵字保留原本的註冊流程，不送給 LLM。
        if text in REGISTER_KEYWORDS:
            line_bot_api.reply_message(
                event.reply_token,
                build_register_message(user_id)
            )
            return

        # 其他訊息交給 LLM；先查真實會員資料與優惠券明細一併提供，
        # 避免被問「我的會員等級」「我有哪些優惠券」之類問題時，因為沒有資料而答不出來。
        member = _fetch_member_by_line_user_id(user_id)
        coupons = None
        if member:
            try:
                coupons = prepare_member_coupon_rows(
                    get_member_coupons(
                        member_id=member["member_id"],
                        limit=50,
                    ),
                    now=datetime.now(),
                )
            except Exception as e:
                print("查詢會員優惠券明細失敗：", e)

        reply_text = ask_llm(
            text,
            member=member,
            coupons=coupons,
        )
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )


@line_bp.route("/line/staff/callback", methods=["POST"])
def staff_callback():
    if not STAFF_LINE_ENABLED:
        return "OK (staff test mode)"

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        staff_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


if STAFF_LINE_ENABLED:
    @staff_handler.add(FollowEvent)
    def handle_staff_follow(event):
        print("店員 Bot 加好友，userId:", event.source.user_id)

    @staff_handler.add(MessageEvent, message=TextMessage)
    def handle_staff_message(event):
        # 這裡的目的只是為了讓你能在後台 log 看到店員自己的 userId
        print("店員 Bot 收到訊息:", event.message.text)
        print("店員 userId:", event.source.user_id)

        staff_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已收到，你的 userId 是：{event.source.user_id}")
        )


def _fetch_member_by_line_user_id(line_user_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id, name, phone, birthday, vip, member_level, "
            "total_visit_count AS visit_count, "
            "line_user_id, total_amount, favorite_product, face_image, created_at, updated_at "
            "FROM members WHERE line_user_id = %s",
            (line_user_id,)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _fetch_member_by_id(member_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id, name, phone, birthday, vip, member_level, "
            "total_visit_count AS visit_count, "
            "line_user_id, total_amount, favorite_product, face_image, created_at, updated_at "
            "FROM members WHERE member_id = %s",
            (member_id,)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _bind_unbound_member_line(member_id, line_user_id, phone):
    """Bind a face-matched legacy member without allowing account takeover."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id, phone, line_user_id FROM members "
            "WHERE member_id = %s FOR UPDATE",
            (member_id,),
        )
        member = cursor.fetchone()
        if not member or member.get("line_user_id"):
            conn.rollback()
            return False
        stored_phone = (member.get("phone") or "").strip()
        if not phone or not stored_phone or phone.strip() != stored_phone:
            conn.rollback()
            return False
        cursor.execute(
            "SELECT member_id FROM members WHERE line_user_id = %s LIMIT 1",
            (line_user_id,),
        )
        if cursor.fetchone() is not None:
            conn.rollback()
            return False
        cursor.execute(
            "UPDATE members SET line_user_id = %s, updated_by = %s, "
            "updated_at = NOW() WHERE member_id = %s AND line_user_id IS NULL",
            (line_user_id, "line_secure_rebind", member_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        conn.commit()
        return True
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _fetch_member_by_phone(phone):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id FROM members WHERE phone = %s",
            (phone,)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _insert_member_preferences(member_id, preferences):
    """將註冊時勾選的喜好項目寫入既有的 member_preferences 表（db 組建立）。"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for value in preferences:
            cursor.execute(
                "INSERT INTO member_preferences (member_id, preference_value, source) "
                "VALUES (%s, %s, %s)",
                (member_id, value, "line")
            )
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"會員喜好寫入失敗（member_id={member_id}）：", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _issue_registration_welcome_coupon_safely(member_id):
    try:
        return issue_registration_welcome_coupon(member_id)
    except Exception as error:
        print(f"新會員 100 元註冊禮發送失敗（member_id={member_id}）：", error)
        return None


def _decode_line_id_token(id_token, channel_id=None):
    """
    向 LINE 官方驗證 ID Token 是否有效，成功時回傳 token 本身認證出的 line_user_id
    （payload 的 sub 欄位）。呼叫端不需要、也不應該自己另外傳一個 line_user_id 來比對，
    直接信任 token 解出來的 sub，才能保證查到的一定是「這支 token 的真正主人」，
    不會被竄改網址/參數影響（例如 /api/coupons/me 用這個查自己的優惠券）。

    回傳 (line_user_id 或 None, 失敗訊息或 None)。
    """
    if not id_token:
        return None, "缺少 LINE 登入憑證，請從 LINE 官方帳號重新開啟頁面"

    expected_channel_id = channel_id or LIFF_CHANNEL_ID

    if not expected_channel_id:
        return None, "LIFF_ID 尚未設定，請聯絡管理員設定後再試"

    try:
        resp = requests.post(
            LINE_VERIFY_URL,
            data={
                "id_token": id_token,
                "client_id": expected_channel_id,
            },
            timeout=5,
        )
    except requests.RequestException as e:
        print("LINE ID Token 驗證服務呼叫失敗：", e)
        return None, "LINE 登入驗證服務暫時無法使用，請稍後再試"

    if resp.status_code != 200:
        print("LINE ID Token 驗證失敗：", resp.status_code, resp.text)
        return None, "LINE 登入已過期或無效，請重新登入後再試"

    payload = resp.json()

    if str(payload.get("aud")) != str(expected_channel_id):
        print("LINE ID Token aud 不符：", payload.get("aud"))
        return None, "LINE 登入驗證失敗，請重新登入後再試"

    line_user_id = payload.get("sub")
    if not line_user_id:
        return None, "LINE 登入驗證失敗，請重新登入後再試"

    return line_user_id, None


def _decode_line_access_token(access_token):
    """使用 LINE access token 查詢本人 profile，安全取得 line_user_id。"""
    if not access_token:
        return None, "缺少 LINE 登入憑證，請從 LINE 官方帳號重新開啟頁面"

    try:
        resp = requests.get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
    except requests.RequestException as e:
        print("LINE Profile 驗證服務呼叫失敗：", e)
        return None, "LINE 登入驗證服務暫時無法使用，請稍後再試"

    if resp.status_code != 200:
        print("LINE Profile 驗證失敗：", resp.status_code, resp.text)
        return None, "LINE 登入已過期或無效，請重新登入後再試"

    line_user_id = (resp.json().get("userId") or "").strip()
    if not line_user_id:
        return None, "LINE 登入驗證失敗，請重新登入後再試"

    return line_user_id, None


def _verify_line_id_token(id_token, expected_line_user_id):
    """
    向 LINE 官方驗證前端傳來的 ID Token，確認註冊請求真的來自 LIFF 登入，
    而不是有人直接偽造/竄改 hidden input 或網址上的 line_user_id。

    回傳 (是否驗證成功, 失敗訊息或 None)。
    """
    line_user_id, error = _decode_line_id_token(id_token)

    if error:
        return False, error

    if line_user_id != expected_line_user_id:
        print("LINE ID Token sub 與送出的 line_user_id 不一致：", line_user_id, expected_line_user_id)
        return False, "LINE 使用者身分驗證失敗，請重新登入後再試"

    return True, None


@line_bp.route("/line/register", methods=["POST"])
def register_from_line():
    """
    LINE 會員註冊 API（LINE 組自己的端點，只用 database.db 既有的 get_connection）。
    line_user_id 是使用者透過 LIFF 登入後，由前端 register.js 呼叫 liff.getProfile() 取得的。

    第三週改版：改收 multipart/form-data，新會員必須附上 face_image 照片才能完成人臉建檔，
    照片只要沒偵測到人臉、偵測到多張臉、或建檔失敗，整筆註冊都會撤銷（不留殘缺會員資料）。

    回傳格式統一為 {"success": bool, "message": str, ...}，方便前端直接顯示 message。
    preferences 會寫入既有的 member_preferences 表。
    """
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    birthday = (request.form.get("birthday") or "").strip() or None
    line_user_id = (request.form.get("line_user_id") or "").strip() or None
    face_image_file = request.files.get("face_image")

    try:
        preferences = json.loads(request.form.get("preferences", "[]"))
        if not isinstance(preferences, list):
            preferences = []
    except (TypeError, ValueError):
        preferences = []

    if not name:
        return jsonify({"success": False, "message": "請輸入姓名"}), 400

    if not line_user_id:
        return jsonify({"success": False, "message": "缺少 LINE 使用者資訊，請從 LINE 官方帳號的註冊連結進入此頁面"}), 400

    # 正式模式下，line_user_id 不能只靠前端傳來的 hidden input／網址參數，
    # 一律要求前端一併送出 LIFF ID Token，由後端向 LINE 驗證身分後才放行。
    # 測試模式（未設定 LINE_CHANNEL_ACCESS_TOKEN/SECRET）維持不驗證，方便本機開發。
    if LINE_ENABLED:
        id_token = (request.form.get("id_token") or "").strip()
        token_ok, token_error = _verify_line_id_token(id_token, line_user_id)
        if not token_ok:
            return jsonify({"success": False, "message": token_error}), 401

    try:
        member = _fetch_member_by_line_user_id(line_user_id)
    except Exception as e:
        print("會員查詢失敗：", e)
        return jsonify({"success": False, "message": "註冊失敗，請稍後再試"}), 500

    if member is not None:
        return jsonify({
            "success": True,
            "message": "您已經是會員囉，這是您目前的會員資料",
            "is_new": False,
            "member": member,
        })

    if phone:
        try:
            phone_owner = _fetch_member_by_phone(phone)
        except Exception as e:
            print("手機號碼查詢失敗：", e)
            return jsonify({"success": False, "message": "註冊失敗，請稍後再試"}), 500

        if phone_owner is not None:
            return jsonify({"success": False, "message": "此手機號碼已經註冊過會員"}), 409

    if not face_image_file or not face_image_file.filename:
        return jsonify({"success": False, "message": "請上傳您的照片以完成人臉建檔"}), 400

    ext = os.path.splitext(face_image_file.filename)[1].lower()
    if ext not in ALLOWED_FACE_IMAGE_EXTENSIONS:
        return jsonify({"success": False, "message": "照片格式不支援，請上傳 jpg 或 png 檔"}), 400

    if face_image_file.mimetype not in ALLOWED_FACE_IMAGE_MIME_TYPES:
        return jsonify({"success": False, "message": "照片格式不支援，請上傳 jpg 或 png 檔"}), 400

    os.makedirs(MEMBER_IMAGE_DIR, exist_ok=True)
    saved_filename = f"line_{uuid.uuid4().hex}{ext}"
    image_path = os.path.join(MEMBER_IMAGE_DIR, saved_filename)
    stored_image_path = None
    member_registered = False
    face_image_file.save(image_path)

    face_check = validate_member_face_image(image_path)
    if not face_check.get("success"):
        os.remove(image_path)
        return jsonify({"success": False, "message": face_check.get("message", "照片驗證失敗")}), 400

    duplicate_result = check_duplicate_face(face_check.get("encoding"))
    if duplicate_result.get("is_duplicate"):
        duplicate_member_id = duplicate_result.get("member_id")
        duplicate_member = _fetch_member_by_id(duplicate_member_id)
        if (
            duplicate_member
            and not duplicate_member.get("line_user_id")
            and _bind_unbound_member_line(
                duplicate_member_id,
                line_user_id,
                phone,
            )
        ):
            if os.path.exists(image_path):
                os.remove(image_path)
            member = _fetch_member_by_id(duplicate_member_id)
            return jsonify({
                "success": True,
                "message": "已確認原會員身分並完成 LINE 綁定",
                "is_new": False,
                "member": member,
            })
        os.remove(image_path)
        return jsonify({
            "success": False,
            "message": "此人臉已經註冊過會員，請勿重複註冊",
            "duplicate_member_id": duplicate_result.get("member_id"),
        }), 409

    try:
        stored_image_path = persist_member_image(
            image_path,
            saved_filename,
            content_type=face_image_file.mimetype,
        )
        if (
            stored_image_path != image_path
            and os.path.isfile(image_path)
        ):
            os.remove(image_path)
    except Exception as storage_error:
        if os.path.isfile(image_path):
            os.remove(image_path)
        print("會員照片持久化失敗：", storage_error)
        return jsonify({
            "success": False,
            "message": "照片儲存失敗，請稍後再試",
        }), 500

    # 用註冊照片的人臉比對是否為既有散客
    visitor_match = find_matching_visitor(
        face_check.get("encoding")
    )
    if visitor_match.get("matched"):
        try:
            convert_result = convert_visitor_to_member(
                visitor_id=visitor_match["visitor_id"],
                name=name,
                phone=phone,
                birthday=birthday,
                line_user_id=line_user_id,
                registration_source="line_visitor_conversion",
                registration_image_path=stored_image_path,
                registration_encoding=face_check.get("encoding"),
                display_face_image=stored_image_path,
            )
        except ValueError as e:
            _cleanup_registration_image(
                image_path,
                stored_image_path,
            )
            print("散客轉會員失敗：", e)
            return jsonify({"success": False, "message": str(e)}), 409
        except Exception as e:
            _cleanup_registration_image(
                image_path,
                stored_image_path,
            )
            print("散客轉會員發生未預期錯誤：", flush=True)
            traceback.print_exc()
            return jsonify({
                "success": False,
                "message": (
                    "散客轉會員失敗，請稍後再試。"
                ),
            }), 500

        member_id = convert_result["member_id"]
        member_registered = True
        reload_member_faces()
        reload_visitor_faces()
        sync_converted_visitor_cache(
            visitor_id=visitor_match["visitor_id"],
            member_id=member_id,
            registration_encoding=face_check.get("encoding"),
            registration_image_path=stored_image_path,
        )

        # 延遲匯入以避免 routes 模組載入時產生循環依賴。
        from routes.camera import convert_visitor_active_visit
        convert_visitor_active_visit(
            visitor_id=visitor_match["visitor_id"],
            member_id=member_id,
            name=name,
            vip=False,
            member_level="normal",
            line_user_id=line_user_id,
            converted_active_log_id=convert_result.get(
                "converted_active_log_id"
            ),
        )

        # 延遲匯入以避免 routes 模組載入時產生循環依賴。
        from routes.camera import clear_visitor_active_visit
        clear_visitor_active_visit(visitor_match["visitor_id"])

        if preferences:
            _insert_member_preferences(member_id, preferences)

        welcome_coupon = _issue_registration_welcome_coupon_safely(member_id)

        member = _fetch_member_by_id(member_id)

        push_message(
            line_user_id,
            f"{name} 您好，歡迎加入會員！記得下次到店讓我們認出您 😊"
        )

        return jsonify({
            "success": True,
            "message": "散客已成功轉為正式會員",
            "is_new": True,
            "converted_from_visitor": True,
            "visitor_id": visitor_match["visitor_id"],
            "visitor_code": visitor_match["visitor_code"],
            "member_id": member_id,
            "member": member,
            "welcome_coupon": welcome_coupon,
        })

    try:
        register_result = register_member_with_face(
            name=name,
            phone=phone,
            birthday=birthday,
            member_level="normal",
            line_user_id=line_user_id,
            face_image=stored_image_path,
            registration_source="line",
            image_path=stored_image_path,
            encoding_data=face_check.get("encoding"),
        )
    except Exception as e:
        if not member_registered:
            _cleanup_registration_image(
                image_path,
                stored_image_path,
            )

        print("========== 會員與人臉註冊完整錯誤 ==========", flush=True)
        traceback.print_exc()
        print(f"錯誤類型：{type(e).__name__}", flush=True)
        print(f"錯誤內容：{e}", flush=True)

        return jsonify({
            "success": False,
            "message": f"會員註冊失敗：{type(e).__name__}：{e}"
        }), 500

    member_id = register_result["member_id"]
    member_registered = True
    reload_member_faces()

    if preferences:
        _insert_member_preferences(member_id, preferences)

    welcome_coupon = _issue_registration_welcome_coupon_safely(member_id)

    member = _fetch_member_by_id(member_id)

    push_message(
        line_user_id,
        f"{name} 您好，歡迎加入會員！記得下次到店讓我們認出您 😊"
    )

    return jsonify({
        "success": True,
        "message": "會員註冊成功",
        "is_new": True,
        "member": member,
        "welcome_coupon": welcome_coupon,
    })


@line_bp.route("/api/notify/vip", methods=["POST"])
def notify_vip():
    """提供不經攝影機也能測試 VIP 到店通知的 API。"""
    data = request.get_json(silent=True) or {}
    member_id = data.get("member_id")
    if not member_id:
        return jsonify({"success": False, "message": "缺少 member_id"}), 400

    try:
        member = _fetch_member_by_id(member_id)
    except Exception as e:
        print(f"查詢會員失敗（member_id={member_id}）：", e)
        return jsonify({"success": False, "message": "查詢會員失敗"}), 500

    if member is None:
        return jsonify({"success": False, "message": "找不到這位會員"}), 404
    if not member.get("vip"):
        return jsonify({
            "success": True,
            "notified": False,
            "message": "此會員不是 VIP，未發送通知",
        })

    notify_status = notify_vip_recognition({
        "member_id": member.get("member_id"),
        "name": member.get("name"),
        "vip": member.get("vip"),
        "member_level": member.get("member_level"),
        "line_user_id": member.get("line_user_id"),
        "confidence": data.get("confidence", 1.0),
        "notification_image_url": data.get("notification_image_url"),
    })
    return jsonify({
        "success": True,
        "notified": True,
        "status": notify_status,
    })


@line_bp.route("/api/lottery/draw", methods=["POST"])
def lottery_draw():
    """
    抽獎 API，給前端 register.js 呼叫取代原本的 Math.random() 假抽獎。
    實際抽獎邏輯（權重、庫存扣除、是否已抽過最終獎項）都在
    database.db.draw_lottery_for_member 裡處理，這裡只負責收請求、轉發、回傳結果。
    """
    data = request.get_json(silent=True) or {}
    member_id = data.get("member_id")
    id_token = (data.get("id_token") or "").strip()
    access_token = (data.get("access_token") or "").strip()

    if not member_id:
        return jsonify({"success": False, "message": "缺少 member_id"}), 400

    if id_token:
        authenticated_line_user_id, auth_error = _decode_line_id_token(
            id_token,
            channel_id=LIFF_CHANNEL_ID,
        )
        if auth_error and access_token:
            authenticated_line_user_id, auth_error = _decode_line_access_token(
                access_token
            )
    else:
        authenticated_line_user_id, auth_error = _decode_line_access_token(
            access_token
        )

    if auth_error:
        return jsonify({"success": False, "message": auth_error}), 401

    member = _fetch_member_by_id(member_id)
    if not member or not member.get("line_user_id"):
        return jsonify({
            "success": False,
            "message": "此會員尚未綁定 LINE，請先完成會員綁定再抽獎",
        }), 409
    if member.get("line_user_id") != authenticated_line_user_id:
        return jsonify({
            "success": False,
            "message": "LINE 登入身分與會員資料不一致，無法抽獎",
        }), 403

    try:
        result = draw_lottery_for_member(member_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        print("抽獎失敗：", e)
        return jsonify({"success": False, "message": "抽獎失敗，請稍後再試"}), 500

    if result.get("success"):
        if member:
            notify_lottery_result(member.get("line_user_id"), member.get("name"), result)

    return jsonify(result)


@line_bp.route("/api/lottery/result/<int:member_id>", methods=["GET"])
def lottery_result(member_id):
    """取得會員既有的抽獎結果與兌換資料。"""
    try:
        prize_record = get_member_prize(member_id)
    except Exception as e:
        print(f"查詢會員抽獎結果失敗（member_id={member_id}）：", e)
        return jsonify({
            "success": False,
            "message": "查詢抽獎結果失敗",
        }), 500

    if prize_record is None:
        return jsonify({
            "success": True,
            "has_result": False,
            "data": None,
        })

    prize_name = get_lottery_prize_display_name(
        prize_record["prize_code"],
        prize_record["prize_name"],
    )
    redeem_token = prize_record["redeem_token"]
    qr_value = f"{REDEMPTION_BASE_URL}/redeem/{redeem_token}"

    def _iso(value):
        return value.isoformat() if value else None

    return jsonify({
        "success": True,
        "has_result": True,
        "data": {
            "prize_code": prize_record["prize_code"],
            "prize_name": prize_name,
            "prize_type": prize_record["prize_type"],
            "prize_value": prize_record["prize_value"],
            "qr_code": qr_value,
            "redeem_token": redeem_token,
            "redeemed": prize_record["status"] == "redeemed",
            "status": prize_record["status"],
            "issued_at": _iso(prize_record["issued_at"]),
            "expires_at": _iso(prize_record["expires_at"]),
            "redeemed_at": _iso(prize_record["redeemed_at"]),
        },
    })


COUPON_EXPIRING_SOON_DAYS = 7


def _fetch_member_coupons_without_redemption(member_id, limit=500):
    """
    舊版正式資料庫的 member_prizes 尚未有 member_coupon_id 時使用。

    會員專區仍可顯示身分與優惠券；只有依賴該欄位的兌換資訊留空。
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                mc.member_coupon_id,
                mc.member_id,
                m.name AS member_name,
                mc.coupon_id,
                c.coupon_name,
                c.description,
                c.discount_type,
                c.discount_value,
                c.start_at,
                c.end_at,
                c.status AS coupon_status,
                mc.source,
                mc.status,
                mc.receive_time,
                mc.used_time,
                NULL AS redeem_token,
                NULL AS redemption_status,
                NULL AS redemption_expires_at
            FROM member_coupons mc
            JOIN members m
                ON mc.member_id = m.member_id
            JOIN coupons c
                ON mc.coupon_id = c.coupon_id
            WHERE mc.member_id = %s
            ORDER BY mc.receive_time DESC,
                     mc.member_coupon_id DESC
            LIMIT %s
            """,
            (member_id, min(max(int(limit), 1), 500)),
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_my_coupon_summary():
    """
    優惠券頁面（/coupons）用：依 LIFF ID Token 或 access token 驗證出
    真正的 line_user_id，
    再查「這個 LINE 使用者自己」的優惠券統計。

    刻意不接受前端直接傳 member_id 或 line_user_id 當參數——一律從已驗證的
    LINE 官方回傳的身分解出 line_user_id，避免有人竄改請求內容看到別人的
    優惠券資料。
    """
    data = request.get_json(silent=True) or {}
    id_token = (data.get("id_token") or "").strip()
    access_token = (data.get("access_token") or "").strip()

    if id_token:
        line_user_id, error = _decode_line_id_token(
            id_token,
            channel_id=LIFF_COUPONS_CHANNEL_ID,
        )
        # 有些 LINE 內建瀏覽器會保留過期的 ID Token，但同一個 LIFF
        # session 的 access token 仍有效。此時改向 LINE Profile API
        # 驗證，避免使用者卡在反覆重新登入。
        if error and access_token:
            line_user_id, error = _decode_line_access_token(access_token)
    else:
        line_user_id, error = _decode_line_access_token(access_token)

    if error:
        return jsonify({"success": False, "message": error}), 401

    try:
        member = _fetch_member_by_line_user_id(line_user_id)
    except Exception as e:
        print("查詢會員失敗：", e)
        return jsonify({"success": False, "message": "查詢失敗，請稍後再試"}), 500

    if member is None:
        return jsonify({
            "success": True,
            "bound": False,
            "message": "此 LINE 帳號尚未綁定會員，請先完成會員註冊",
        })

    prizes = []
    try:
        coupons = get_member_coupons(member_id=member["member_id"], limit=500)
        prizes = get_member_non_coupon_prizes(
            member_id=member["member_id"],
            limit=500,
        )
    except Exception as e:
        error_text = str(e)
        if (
            "Unknown column" in error_text
            and "mp.member_coupon_id" in error_text
        ):
            try:
                coupons = _fetch_member_coupons_without_redemption(
                    member_id=member["member_id"],
                    limit=500,
                )
            except Exception as fallback_error:
                print("相容模式查詢會員優惠券失敗：", fallback_error)
                return jsonify({
                    "success": False,
                    "message": "查詢失敗，請稍後再試",
                }), 500
        else:
            print("查詢會員優惠券失敗：", e)
            return jsonify({
                "success": False,
                "message": "查詢失敗，請稍後再試",
            }), 500

    now = datetime.now()
    soon = now + timedelta(days=COUPON_EXPIRING_SOON_DAYS)

    prepared_coupons = prepare_member_coupon_rows(
        coupons,
        now=now,
        include_redemption=True
    )
    usable = 0
    expiring_soon = 0

    for coupon in prepared_coupons:
        if coupon.get("status_key") != "available":
            continue

        usable += 1

        end_at = coupon.get("end_at")
        if end_at and now <= end_at <= soon:
            expiring_soon += 1

    return jsonify({
        "success": True,
        "bound": True,
        "total": len(coupons),
        "usable": usable,
        "expiring_soon": expiring_soon,
        "coupons": [
            {
                "member_coupon_id": coupon.get(
                    "member_coupon_id"
                ),
                "coupon_name": coupon.get("coupon_name"),
                "description": coupon.get("description"),
                "discount_text": coupon.get("discount_text"),
                "receive_time": coupon.get("receive_time_text"),
                "end_at": coupon.get("end_at_text"),
                "status": coupon.get("status_key"),
                "status_label": coupon.get("status_label"),
                "used_time": coupon.get("used_time_text"),
                "redemption_info": coupon.get(
                    "redemption_info"
                ),
                "can_open_redemption": coupon.get(
                    "can_open_redemption",
                    False
                ),
                "redeem_url": coupon.get("redeem_url"),
            }
            for coupon in prepared_coupons
        ],
        "prizes": [
            {
                "member_prize_id": prize.get("member_prize_id"),
                "prize_name": prize.get("prize_name"),
                "prize_code": prize.get("prize_code"),
                "status": prize.get("status"),
                "issued_at": (
                    prize.get("issued_at").strftime("%Y-%m-%d %H:%M:%S")
                    if prize.get("issued_at") else ""
                ),
                "expires_at": (
                    prize.get("expires_at").strftime("%Y-%m-%d %H:%M:%S")
                    if prize.get("expires_at") else ""
                ),
                "redeem_url": (
                    f"/redeem/{prize.get('redeem_token')}"
                    if prize.get("redeem_token") else None
                ),
            }
            for prize in prizes
        ],
    })


@line_bp.route("/redeem/<token>", methods=["GET", "POST"])
def redeem_prize(token):
    """
    店員核銷頁面：客人手機上中獎 QR Code 掃出來的網址就是這裡。
    店員確認會員與獎項資訊無誤後，輸入自己的姓名/工號完成核銷。
    純內部工具頁面，跟 routes/member.py 其他後台頁面一樣沒有另外做登入驗證。
    """
    if request.method == "POST":
        redeemed_by = (request.form.get("redeemed_by") or "").strip()

        if not redeemed_by:
            return "請輸入核銷人員姓名，才能完成核銷。", 400

        try:
            result = redeem_member_prize(token, redeemed_by)
        except Exception as e:
            print("核銷失敗：", e)
            return "核銷失敗，請稍後再試", 500

        if not result.get("success"):
            return f"""
            <h1>核銷失敗</h1>
            <p>{escape(result.get("message", "核銷失敗"))}</p>
            <p><a href="/redeem/{escape(token)}">重新整理再試一次</a></p>
            """

    try:
        redemption = get_redemption_by_token(token)
    except Exception as e:
        print("查詢兌換資料失敗：", e)
        return "查詢失敗，請稍後再試", 500

    if redemption is None:
        return "找不到這張兌換 QR Code，請確認連結是否正確。", 404

    member_name = escape(redemption.get("member_name") or "")
    member_phone = escape(redemption.get("member_phone") or "")
    prize_name = escape(redemption.get("prize_name") or "")
    status = redemption.get("status")
    expires_at = redemption.get("expires_at")
    is_expired = bool(expires_at) and expires_at <= datetime.now()

    if status == "redeemed":
        return f"""
        <h1>這張獎項已經核銷過了</h1>
        <p>會員：{member_name}（{member_phone}）</p>
        <p>獎項：{prize_name}</p>
        <p>核銷時間：{redemption.get("redeemed_at")}</p>
        <p>核銷人員：{escape(redemption.get("redeemed_by") or "")}</p>
        """

    if status == "expired" or is_expired:
        return f"""
        <h1>這張獎項已經過期</h1>
        <p>會員：{member_name}（{member_phone}）</p>
        <p>獎項：{prize_name}</p>
        <p>兌換期限：{expires_at}</p>
        """

    return f"""
    <h1>會員兌換核銷</h1>
    <p>會員：{member_name}（{member_phone}）</p>
    <p>獎項：{prize_name}</p>
    <p>兌換期限：{expires_at if expires_at else "無期限"}</p>

    <form method="POST">
        <p>
            核銷人員（姓名或工號）：
            <input type="text" name="redeemed_by" required>
        </p>
        <button type="submit">確認核銷</button>
    </form>
    """


def _fetch_members_crossing_vip_threshold(threshold):
    """查詢累積消費達門檻、但還不是 VIP 的會員。"""
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT member_id, name, line_user_id, total_amount "
            "FROM members "
            "WHERE total_amount >= %s AND (vip = FALSE OR vip IS NULL)",
            (threshold,)
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _mark_member_as_vip(member_id):
    """
    把會員標記為 VIP，member_level 一併同步成 'vip'
    （跟 routes/member.py 既有的 member_level = "vip" if vip else "normal" 邏輯一致）。
    """
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE members SET vip = TRUE, member_level = 'vip', updated_by = 'vip_auto_upgrade' "
            "WHERE member_id = %s",
            (member_id,)
        )
        conn.commit()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@line_bp.route("/line/cron/vip-check", methods=["POST"])
def vip_upgrade_cron():
    """
    給 Cloud Scheduler 每天固定時間呼叫：撈出累積消費達 VIP_UPGRADE_THRESHOLD、
    但還不是 VIP 的會員，標記為 VIP 並推播升級通知。查詢條件用 vip = FALSE，
    所以已經是 VIP 的會員不會被重複撈到，也就不會每天重複推播。

    用 X-Cron-Secret header 驗證，沒帶對密鑰一律 403，避免任何人從外部
    直接打這支 API 觸發批次升級。
    """
    if not CRON_SECRET or request.headers.get("X-Cron-Secret") != CRON_SECRET:
        abort(403)

    try:
        candidates = _fetch_members_crossing_vip_threshold(VIP_UPGRADE_THRESHOLD)
    except Exception as e:
        print("VIP 升級檢查查詢失敗：", e)
        return jsonify({"success": False, "message": "查詢失敗"}), 500

    upgraded = []
    failed = []

    for member in candidates:
        member_id = member["member_id"]

        try:
            _mark_member_as_vip(member_id)
        except Exception as e:
            print(f"VIP 升級失敗（member_id={member_id}）：", e)
            failed.append(member_id)
            continue

        upgraded.append(member_id)
        notify_vip_upgrade({
            "member_id": member_id,
            "name": member.get("name"),
            "line_user_id": member.get("line_user_id"),
        })

    return jsonify({
        "success": True,
        "checked": len(candidates),
        "upgraded": upgraded,
        "failed": failed,
    })
