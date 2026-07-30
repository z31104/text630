import unittest
from datetime import datetime
from unittest.mock import patch

from app import app
from routes import camera


class CurrentVisitorsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_returns_current_visitors(self):
        rows = [{
            "log_id": 25,
            "subject_type": "visitor",
            "member_id": None,
            "visitor_id": 7,
            "visitor_code": "V000007",
            "name": "固定散客 V000007",
            "vip": False,
            "confidence": 0.81,
            "member_level": "guest",
            "member_level_text": "散客",
            "recognition_status": "recognized",
            "visit_status": "staying",
            "camera_id": "camera_1",
            "camera_location": "入口",
            "visit_time": datetime(2026, 7, 29, 11, 0, 0),
            "last_seen_at": datetime(2026, 7, 29, 11, 0, 30),
            "leave_time": None,
            "stay_seconds": 30,
            "stay_minutes": 0.5,
        }]

        with patch(
            "routes.camera.get_current_visitors",
            return_value=rows,
        ) as mocked_query:
            response = self.client.get("/api/current-visitors")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json(), {
            "success": True,
            "current_visitors": [{
                "log_id": 25,
                "subject_type": "visitor",
                "member_id": None,
                "visitor_id": 7,
                "visitor_code": "V000007",
                "name": "固定散客 V000007",
                "vip": False,
                "confidence": 0.81,
                "member_level": "guest",
                "member_level_text": "散客",
                "recognition_status": "recognized",
                "visit_status": "staying",
                "camera_id": "camera_1",
                "camera_location": "入口",
                "visit_time": "2026-07-29T11:00:00",
                "last_seen_at": "2026-07-29T11:00:30",
                "leave_time": None,
                "stay_seconds": 30,
                "stay_minutes": 0.5,
            }],
            "count": 1,
        })
        mocked_query.assert_called_once_with(
            timeout_seconds=camera.LEAVE_TIMEOUT,
        )

    def test_returns_empty_list_when_store_is_empty(self):
        with patch(
            "routes.camera.get_current_visitors",
            return_value=[],
        ):
            response = self.client.get("/api/current-visitors")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "success": True,
            "current_visitors": [],
            "count": 0,
        })

    def test_returns_safe_error_when_database_query_fails(self):
        with patch(
            "routes.camera.get_current_visitors",
            side_effect=RuntimeError("database details"),
        ):
            response = self.client.get("/api/current-visitors")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {
            "success": False,
            "message": "無法取得目前店內人員",
        })


if __name__ == "__main__":
    unittest.main()
