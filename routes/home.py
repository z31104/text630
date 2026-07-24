from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request

try:
    from database.db import (
        get_coupon_summary,
        get_dashboard_summary,
        get_member_coupons,
        get_recognition_logs,
    )
except ImportError:
    get_coupon_summary = None
    get_dashboard_summary = None
    get_member_coupons = None
    get_recognition_logs = None

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


@home_bp.route("/coupons")
def coupons():
    member_id = _optional_positive_int(request.args.get("member_id"))
    summary, summary_error = _safe_fetch(get_coupon_summary, {})
    member_coupon_summary = None
    coupons_error = None

    if member_id is not None:
        coupon_rows, coupons_error = _safe_fetch(
            get_member_coupons,
            [],
            member_id=member_id,
            limit=500,
        )

        today = date.today()
        expiring_cutoff = today + timedelta(days=7)
        available_coupons = [
            coupon for coupon in coupon_rows
            if coupon.get("status") == "unused"
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
        selected_member_id=member_id,
        load_error=coupons_error if member_id is not None else summary_error,
    )


@home_bp.route("/register")
def register():
    return render_template("register.html")
