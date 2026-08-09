from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, url_for

try:
    from database.db import (
        get_coupon_summary,
        get_dashboard_summary,
        get_member_coupons,
        get_recognition_logs,
        get_seven_day_visit_trend,
        get_visit_hour_distribution,
    )
except ImportError:
    get_coupon_summary = None
    get_dashboard_summary = None
    get_member_coupons = None
    get_recognition_logs = None
    get_seven_day_visit_trend = None
    get_visit_hour_distribution = None

home_bp = Blueprint("home", __name__)


def _safe_fetch(fetch_fn, fallback, *args, **kwargs):
    if fetch_fn is None:
        return fallback, "資料來源尚未提供，請聯絡整合組確認。"

    try:
        result = fetch_fn(*args, **kwargs)
        if result is None:
            return fallback, None
        return result, None
    except Exception as e:
        print("前端頁面資料讀取失敗：", e)
        return fallback, "資料載入失敗，請稍後再試。"


def _optional_positive_int(value):
    if value is None or str(value).strip() == "":
        return None

    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        return None

    return parsed_value if parsed_value > 0 else None


def _coupon_end_date(value):
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None

    return None


def _coupon_datetime(value):
    if isinstance(value, datetime):
        parsed_value = value
    elif isinstance(value, date):
        parsed_value = datetime.combine(value, datetime.max.time())
    elif value:
        try:
            parsed_value = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except ValueError:
            return None
    else:
        return None

    if parsed_value.tzinfo is not None:
        return parsed_value.astimezone().replace(tzinfo=None)

    return parsed_value


def _coupon_datetime_text(value):
    parsed_value = _coupon_datetime(value)

    if parsed_value is None:
        return ""

    return parsed_value.strftime("%Y-%m-%d %H:%M:%S")


def _coupon_number_text(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""

    if number.is_integer():
        return str(int(number))

    return f"{number:g}"


def _coupon_discount_text(coupon):
    discount_type = str(coupon.get("discount_type") or "").lower()
    discount_value = coupon.get("discount_value")
    value_text = _coupon_number_text(discount_value)

    if discount_type == "amount" and value_text:
        return f"折抵 {value_text} 元"

    if discount_type == "percentage" and value_text:
        discounted_percentage = max(
            0,
            100 - float(discount_value)
        )
        return f"享原價 {_coupon_number_text(discounted_percentage)}%"

    if discount_type == "free_shipping":
        return "免運優惠"

    return ""


def prepare_member_coupon_rows(
    coupon_rows,
    now=None,
    include_redemption=False
):
    """
    將既有 get_member_coupons() 結果整理成模板與 LIFF API 共用格式。
    不改寫資料庫狀態；過期判斷只依後端回傳的狀態與有效期限。
    """
    current_time = now or datetime.now()
    prepared_rows = []

    status_labels = {
        "available": "可使用",
        "used": "已使用",
        "expired": "已過期",
        "upcoming": "尚未生效",
        "unavailable": "不可使用",
    }

    for coupon_data in coupon_rows or []:
        coupon = dict(coupon_data)
        member_status = str(coupon.get("status") or "").lower()
        coupon_status = str(
            coupon.get("coupon_status") or "active"
        ).lower()
        redemption_status = str(
            coupon.get("redemption_status") or ""
        ).lower()

        start_at = _coupon_datetime(coupon.get("start_at"))
        end_at = _coupon_datetime(coupon.get("end_at"))
        redemption_expires_at = _coupon_datetime(
            coupon.get("redemption_expires_at")
        )

        is_expired_by_time = any(
            expiry is not None and expiry < current_time
            for expiry in (end_at, redemption_expires_at)
        )

        if (
            member_status == "used"
            or redemption_status == "redeemed"
        ):
            status_key = "used"
        elif (
            member_status == "expired"
            or redemption_status == "expired"
            or is_expired_by_time
        ):
            status_key = "expired"
        elif member_status == "unused":
            if coupon_status != "active":
                status_key = "unavailable"
            elif start_at is not None and start_at > current_time:
                status_key = "upcoming"
            else:
                status_key = "available"
        else:
            status_key = "unavailable"

        redeem_token = coupon.get("redeem_token")
        can_open_redemption = bool(
            include_redemption
            and status_key == "available"
            and redeem_token
        )
        redeem_url = (
            url_for("line.redeem_prize", token=redeem_token)
            if can_open_redemption
            else None
        )

        receive_time_text = _coupon_datetime_text(
            coupon.get("receive_time")
            or coupon.get("issued_at")
        )
        end_at_text = _coupon_datetime_text(coupon.get("end_at"))
        used_time_text = _coupon_datetime_text(
            coupon.get("redeemed_at")
            or coupon.get("used_time")
            or coupon.get("used_at")
        )

        if status_key == "used":
            redemption_info = (
                f"已於 {used_time_text} 完成兌換"
                if used_time_text
                else "已完成兌換"
            )
        elif status_key == "expired":
            redemption_info = "已超過有效期限，不可再次兌換"
        elif status_key == "upcoming":
            redemption_info = "尚未進入使用期間"
        elif status_key == "unavailable":
            redemption_info = "目前不可兌換"
        elif can_open_redemption:
            redemption_info = "可開啟既有兌換入口"
        else:
            redemption_info = "尚未使用"

        coupon.update({
            "status_key": status_key,
            "status_label": status_labels[status_key],
            "discount_text": _coupon_discount_text(coupon),
            "receive_time_text": receive_time_text,
            "end_at_text": end_at_text,
            "used_time_text": used_time_text,
            "redemption_info": redemption_info,
            "can_open_redemption": can_open_redemption,
            "redeem_url": redeem_url,
        })
        prepared_rows.append(coupon)

    return prepared_rows


@home_bp.route("/")
def home():
    return render_template("index.html")


@home_bp.route("/dashboard")
def dashboard():
    summary, summary_error = _safe_fetch(get_dashboard_summary, {})
    recent_recognitions, recognition_error = _safe_fetch(
        get_recognition_logs,
        [],
        limit=500,
    )

    spec_summary_fields = {
        "today_visitors",
        "today_visit_count",
        "today_vip",
        "today_new_members",
        "today_visitors_fixed",
        "current_people",
        "average_stay_minutes",
    }
    dashboard_contract_ready = (
        isinstance(summary, dict)
        and spec_summary_fields.issubset(summary.keys())
    )

    return render_template(
        "dashboard.html",
        summary=summary,
        recent_recognitions=recent_recognitions,
        dashboard_contract_ready=dashboard_contract_ready,
        dashboard_errors={
            "summary": summary_error,
            "recognitions": recognition_error,
        },
    )


@home_bp.route("/api/dashboard/charts", methods=["GET"])
def dashboard_charts_api():
    """
    回傳 Dashboard 圖表需要的資料：
    1. 最近七天到店趨勢
    2. 每小時到店分布
    """
    if (
        get_seven_day_visit_trend is None
        or get_visit_hour_distribution is None
    ):
        return jsonify({
            "success": False,
            "message": "Dashboard 圖表資料來源尚未提供",
            "data": {
                "seven_day_trend": [],
                "hourly_distribution": [],
            },
        }), 503

    try:
        seven_day_trend = get_seven_day_visit_trend()
        hourly_distribution = get_visit_hour_distribution()

        return jsonify({
            "success": True,
            "message": "Dashboard 圖表資料取得成功",
            "data": {
                "seven_day_trend": seven_day_trend or [],
                "hourly_distribution": hourly_distribution or [],
            },
        }), 200

    except Exception as e:
        print("取得 Dashboard 圖表資料失敗：", e)

        return jsonify({
            "success": False,
            "message": "取得 Dashboard 圖表資料失敗",
            "data": {
                "seven_day_trend": [],
                "hourly_distribution": [],
            },
        }), 500



@home_bp.route("/coupons")
def coupons():
    # LINE「我的會員」與管理網頁共用此頁。只在 LINE 內建瀏覽器中
    # 隱藏管理端導覽列，一般瀏覽器的網頁外觀維持不變。
    user_agent = request.headers.get("User-Agent", "")
    is_line_member_view = " line/" in f" {user_agent.lower()}"
    member_id = _optional_positive_int(request.args.get("member_id"))
    summary, summary_error = _safe_fetch(get_coupon_summary, {})
    member_coupon_summary = None
    coupon_rows = []
    coupons_error = None

    if member_id is not None:
        raw_coupon_rows, coupons_error = _safe_fetch(
            get_member_coupons,
            [],
            member_id=member_id,
            limit=500,
        )
        coupon_rows = prepare_member_coupon_rows(raw_coupon_rows)

        today = date.today()
        expiring_cutoff = today + timedelta(days=7)
        available_coupons = [
            coupon for coupon in coupon_rows
            if coupon.get("status_key") == "available"
        ]
        expiring_soon = [
            coupon for coupon in available_coupons
            if (
                (end_date := _coupon_end_date(coupon.get("end_at")))
                and today <= end_date <= expiring_cutoff
            )
        ]
        member_coupon_summary = {
            "total_coupons": len(coupon_rows),
            "available_coupons": len(available_coupons),
            "expiring_soon": len(expiring_soon),
        }

    return render_template(
        "coupons.html",
        summary=summary,
        member_coupon_summary=member_coupon_summary,
        coupon_rows=coupon_rows,
        selected_member_id=member_id,
        load_error=coupons_error if member_id is not None else summary_error,
        is_line_member_view=is_line_member_view,
    )


@home_bp.route("/register")
def register():
    user_agent = request.headers.get("User-Agent", "")
    is_line_register_view = " line/" in f" {user_agent.lower()}"
    return render_template(
        "register.html",
        is_line_register_view=is_line_register_view,
    )
