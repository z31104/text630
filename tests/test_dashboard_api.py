from unittest.mock import patch

from app import app


def test_dashboard_api_success():
    fake_summary = {
        "today_visitors": 6,
        "today_visit_count": 8,
        "today_vip": 3,
        "today_new_members": 1,
        "today_visitors_fixed": 2,
        "current_people": 1,
        "average_stay_minutes": 12.5,
    }

    with app.test_client() as client:
        with patch(
            "routes.home.get_dashboard_summary",
            return_value=fake_summary,
        ):
            response = client.get("/api/dashboard")

    assert response.status_code == 200

    result = response.get_json()

    assert result["success"] is True
    assert result["data"] == fake_summary


def test_dashboard_api_database_error():
    with app.test_client() as client:
        with patch(
            "routes.home.get_dashboard_summary",
            side_effect=RuntimeError("資料庫連線失敗"),
        ):
            response = client.get("/api/dashboard")

    assert response.status_code == 500

    result = response.get_json()

    assert result["success"] is False
    assert result["message"] == "取得 Dashboard 統計資料失敗"