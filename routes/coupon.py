"""
優惠券模組（LINE 組 API 3：Coupon API）。

從 routes/line.py 拆出來的獨立 Blueprint，只放優惠券相關的查詢邏輯：
- POST /api/coupons/me            會員專區頁面用，走 LIFF ID Token 驗證身分
- GET  /api/member/<id>/coupons   文件規格的內部查詢端點，給組長整合／其他組測試用

LIFF 驗證（_decode_line_id_token）跟會員查詢（_fetch_member_by_line_user_id）
是 routes/line.py 註冊流程也在共用的通用工具，所以直接從那邊 import，
沒有重複實作一份。
"""

from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify

from database.db import (
    get_connection,
    get_member_coupons,
    get_member_non_coupon_prizes,
)
from routes.home import prepare_member_coupon_rows
from routes.line import (
    LIFF_ID_COUPONS,
    _decode_line_access_token,
    _decode_line_id_token,
    _fetch_member_by_line_user_id,
)

coupon_bp = Blueprint("coupon", __name__)

# LIFF ID 格式固定是「{LINE Login channel id}-{liff app id}」，
# 驗證 ID Token 的 aud/client_id 要用前半段的 channel id。
LIFF_COUPONS_CHANNEL_ID = (
    LIFF_ID_COUPONS.split("-")[0]
    if LIFF_ID_COUPONS
    else ""
)

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


def _fetch_member_coupons_with_fallback(member_id, limit=500):
    """
    共用查詢邏輯：先走正式版（含兌換資訊），撈不到 member_coupon_id 欄位時
    自動退回相容模式，讓 /api/coupons/me 和文件版端點共用同一套容錯行為。
    """
    try:
        return get_member_coupons(member_id=member_id, limit=limit)
    except Exception as e:
        error_text = str(e)
        if (
            "Unknown column" in error_text
            and "mp.member_coupon_id" in error_text
        ):
            return _fetch_member_coupons_without_redemption(
                member_id=member_id,
                limit=limit,
            )
        raise


@coupon_bp.route("/api/coupons/me", methods=["POST"])
def get_my_coupon_summary():
    """
    優惠券頁面（/coupons）用：依 LIFF ID Token 驗證出真正的 line_user_id，
    再查「這個 LINE 使用者自己」的優惠券統計。

    刻意不接受前端直接傳 member_id 或 line_user_id 當參數——一律從已驗證的
    id_token 解出 line_user_id，避免有人竄改請求內容看到別人的優惠券資料。
    """
    data = request.get_json(silent=True) or {}
    id_token = (data.get("id_token") or "").strip()
    access_token = (data.get("access_token") or "").strip()

    if id_token:
        line_user_id, error = _decode_line_id_token(
            id_token,
            channel_id=LIFF_COUPONS_CHANNEL_ID,
        )
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

    try:
        coupons = _fetch_member_coupons_with_fallback(
            member_id=member["member_id"],
            limit=500,
        )
    except Exception as e:
        print("查詢會員優惠券失敗：", e)
        return jsonify({
            "success": False,
            "message": "查詢失敗，請稍後再試",
        }), 500

    try:
        prizes = get_member_non_coupon_prizes(
            member_id=member["member_id"],
            limit=500,
        )
    except Exception as e:
        print("查詢會員非優惠券獎項失敗：", e)
        prizes = []

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


@coupon_bp.route("/api/member/<int:member_id>/coupons", methods=["GET"])
def get_member_coupons_by_id(member_id):
    """
    文件版 Coupon API（LINE 組 API 3）：GET /api/member/{member_id}/coupons
    回傳：優惠券、是否使用、到期日。

    給組長整合、其他組測試用的內部查詢端點，直接用網址帶 member_id，
    沒有做 LIFF 身分驗證——這點跟資料庫組 GET /api/member/{member_id} 同一種
    定位（內部管理／整合用途，不是給使用者手機直接打的公開端點）。

    會員專區真正給使用者本人用的頁面，走的是上面的 POST /api/coupons/me，
    那支才會驗證 LIFF id_token，避免任何人改網址就看到別人的優惠券。
    這兩支端點並存、分工不同，不要把 /api/coupons/me 改成這種不驗證的寫法。
    """
    try:
        coupons = _fetch_member_coupons_with_fallback(
            member_id=member_id,
            limit=500,
        )
    except Exception as e:
        print(f"查詢會員優惠券失敗（member_id={member_id}）：", e)
        return jsonify({
            "success": False,
            "message": "查詢會員優惠券失敗",
        }), 500

    prepared_coupons = prepare_member_coupon_rows(
        coupons,
        now=datetime.now(),
        include_redemption=False,
    )

    def _iso(text):
        # prepare_member_coupon_rows() 給的是 "YYYY-MM-DD HH:MM:SS"（會員專區頁面共用格式），
        # 這裡只把空格換成 "T"，符合團隊規定的 ISO 8601，不動到共用函式本身。
        return text.replace(" ", "T", 1) if text else text

    return jsonify({
        "success": True,
        "count": len(prepared_coupons),
        "data": [
            {
                "member_coupon_id": coupon.get("member_coupon_id"),
                "coupon_name": coupon.get("coupon_name"),
                "description": coupon.get("description"),
                "discount_text": coupon.get("discount_text"),
                "receive_time": _iso(coupon.get("receive_time_text")),
                "end_at": _iso(coupon.get("end_at_text")),
                "used": coupon.get("status_key") == "used",
                "status": coupon.get("status_key"),
                "status_label": coupon.get("status_label"),
            }
            for coupon in prepared_coupons
        ],
    })
