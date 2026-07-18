from flask import Blueprint, render_template

try:
    from database.db import (
        get_dashboard_summary,
        get_recent_recognitions,
        get_recent_vip_notifications,
    )
except ImportError:
    get_dashboard_summary = None
    get_recent_recognitions = None
    get_recent_vip_notifications = None

home_bp = Blueprint("home", __name__)


def _safe_fetch(fetch_fn, fallback):
    if fetch_fn is None:
        return fallback

    try:
        return fetch_fn() or fallback
    except Exception as e:
        print("Dashboard 資料讀取失敗，改用空資料：", e)
        return fallback

@home_bp.route("/")
def home():
    return render_template("index.html")

@home_bp.route("/dashboard")
def dashboard():
    summary = _safe_fetch(get_dashboard_summary, {})
    recent_recognitions = _safe_fetch(get_recent_recognitions, [])
    recent_vip_notifications = _safe_fetch(
        get_recent_vip_notifications,
        []
    )

    return render_template(
        "dashboard.html",
        summary=summary,
        recent_recognitions=recent_recognitions,
        recent_vip_notifications=recent_vip_notifications,
    )

@home_bp.route("/register")
def register():
    return render_template("register.html")
