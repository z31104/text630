import json
import os
import uuid
from datetime import datetime, timedelta

import requests
from flask import Blueprint, request, abort, jsonify

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
)
from linebot_service.notify import push_message, notify_lottery_result
from services.face_service import (
    validate_member_face_image,
    check_duplicate_face,
    find_matching_visitor,
    reload_member_faces,
    reload_visitor_faces,
    MEMBER_IMAGE_DIR,
)

ALLOWED_FACE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_FACE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}

line_bp = Blueprint("line", __name__)

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

# LIFF ID 格式固定是「{LINE Login channel id}-{liff app id}」，
# 驗證 ID Token 的 aud/client_id 要用前半段的 channel id，不需要另外設定新的環境變數
LIFF_CHANNEL_ID = LIFF_ID.split("-")[0] if LIFF_ID else ""

LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"

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
    """提供前端 register.js 需要的公開設定值（目前只有 LIFF ID）。"""
    return jsonify({"liff_id": LIFF_ID})


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

        # 先印出來，方便你確認有沒有收到訊息、順便記下自己的 userId
        print("收到訊息:", text)
        print("使用者 userId:", user_id)

        if text in REGISTER_KEYWORDS:
            line_bot_api.reply_message(event.reply_token, build_register_message(user_id))
            return

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=event.message.text)
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


def _decode_line_id_token(id_token):
    """
    向 LINE 官方驗證 ID Token 是否有效，成功時回傳 token 本身認證出的 line_user_id
    （payload 的 sub 欄位）。呼叫端不需要、也不應該自己另外傳一個 line_user_id 來比對，
    直接信任 token 解出來的 sub，才能保證查到的一定是「這支 token 的真正主人」，
    不會被竄改網址/參數影響（例如 /api/coupons/me 用這個查自己的優惠券）。

    回傳 (line_user_id 或 None, 失敗訊息或 None)。
    """
    if not id_token:
        return None, "缺少 LINE 登入憑證，請從 LINE 官方帳號重新開啟頁面"

    if not LIFF_CHANNEL_ID:
        return None, "LIFF_ID 尚未設定，請聯絡管理員設定後再試"

    try:
        resp = requests.post(
            LINE_VERIFY_URL,
            data={"id_token": id_token, "client_id": LIFF_CHANNEL_ID},
            timeout=5,
        )
    except requests.RequestException as e:
        print("LINE ID Token 驗證服務呼叫失敗：", e)
        return None, "LINE 登入驗證服務暫時無法使用，請稍後再試"

    if resp.status_code != 200:
        print("LINE ID Token 驗證失敗：", resp.status_code, resp.text)
        return None, "LINE 登入已過期或無效，請重新登入後再試"

    payload = resp.json()

    if payload.get("aud") != LIFF_CHANNEL_ID:
        print("LINE ID Token aud 不符：", payload.get("aud"))
        return None, "LINE 登入驗證失敗，請重新登入後再試"

    line_user_id = payload.get("sub")
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
    face_image_file.save(image_path)

    face_check = validate_member_face_image(image_path)
    if not face_check.get("success"):
        os.remove(image_path)
        return jsonify({"success": False, "message": face_check.get("message", "照片驗證失敗")}), 400

    duplicate_result = check_duplicate_face(face_check.get("encoding"))
    if duplicate_result.get("is_duplicate"):
        os.remove(image_path)
        return jsonify({
            "success": False,
            "message": "此人臉已經註冊過會員，請勿重複註冊",
            "duplicate_member_id": duplicate_result.get("member_id"),
        }), 409

    # 先比對是否為既有散客，命中的話走轉換流程，避免把老客人當成全新會員重建
    visitor_match = find_matching_visitor(face_check.get("encoding"))

    if visitor_match.get("matched"):
        try:
            convert_result = convert_visitor_to_member(
                visitor_id=visitor_match["visitor_id"],
                name=name,
                phone=phone,
                birthday=birthday,
                line_user_id=line_user_id,
                registration_source="line_visitor_conversion",
                registration_image_path=image_path,
                registration_encoding=face_check.get("encoding"),
            )
        except ValueError as e:
            if os.path.exists(image_path):
                os.remove(image_path)
            print("散客轉會員失敗：", e)
            return jsonify({"success": False, "message": str(e)}), 409
        except Exception as e:
            if os.path.exists(image_path):
                os.remove(image_path)
            print("散客轉會員失敗：", e)
            return jsonify({"success": False, "message": "註冊失敗，請稍後再試"}), 500

        member_id = convert_result["member_id"]
        reload_member_faces()
        reload_visitor_faces()

        if preferences:
            _insert_member_preferences(member_id, preferences)

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
            "visitor_id": visitor_match.get("visitor_id"),
            "visitor_code": visitor_match.get("visitor_code"),
            "member_id": member_id,
            "member": member,
        })

    try:
        register_result = register_member_with_face(
            name=name,
            phone=phone,
            birthday=birthday,
            member_level="normal",
            line_user_id=line_user_id,
            face_image=saved_filename,
            registration_source="line",
            image_path=image_path,
            encoding_data=face_check.get("encoding"),
        )
    except Exception as e:
        if os.path.exists(image_path):
            os.remove(image_path)

        print("會員與人臉註冊失敗：", e)

        return jsonify({
            "success": False,
            "message": "註冊失敗，請稍後再試"
        }), 500

    member_id = register_result["member_id"]
    reload_member_faces()

    if preferences:
        _insert_member_preferences(member_id, preferences)

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

    if not member_id:
        return jsonify({"success": False, "message": "缺少 member_id"}), 400

    try:
        result = draw_lottery_for_member(member_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        print("抽獎失敗：", e)
        return jsonify({"success": False, "message": "抽獎失敗，請稍後再試"}), 500

    if result.get("success"):
        member = _fetch_member_by_id(member_id)
        if member:
            notify_lottery_result(member.get("line_user_id"), member.get("name"), result)

    return jsonify(result)


COUPON_EXPIRING_SOON_DAYS = 7


@line_bp.route("/api/coupons/me", methods=["POST"])
def get_my_coupon_summary():
    """
    優惠券頁面（/coupons）用：依 LIFF ID Token 驗證出真正的 line_user_id，
    再查「這個 LINE 使用者自己」的優惠券統計。

    刻意不接受前端直接傳 member_id 或 line_user_id 當參數——一律從已驗證的
    id_token 解出 line_user_id，避免有人竄改請求內容看到別人的優惠券資料。
    """
    data = request.get_json(silent=True) or {}
    id_token = (data.get("id_token") or "").strip()

    line_user_id, error = _decode_line_id_token(id_token)

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

    try:
        coupons = get_member_coupons(member_id=member["member_id"], limit=500)
    except Exception as e:
        print("查詢會員優惠券失敗：", e)
        return jsonify({"success": False, "message": "查詢失敗，請稍後再試"}), 500

    now = datetime.now()
    soon = now + timedelta(days=COUPON_EXPIRING_SOON_DAYS)

    usable = 0
    expiring_soon = 0

    for coupon in coupons:
        if coupon.get("status") != "unused":
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
    })
