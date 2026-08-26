import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from app import app


class RecognitionsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_returns_latest_recognition_records(self):
        rows = [{
            "log_id": 12,
            "subject_type": "member",
            "member_id": 3,
            "visitor_id": None,
            "name": "測試會員",
            "vip": True,
            "confidence": 0.92,
            "visit_time": datetime(2026, 7, 29, 10, 30, 45),
            "stay_minutes": Decimal("1.50"),
            "line_user_id": "private-line-id",
        }]

        with patch(
            "routes.camera.get_recognition_logs",
            return_value=rows,
        ) as mocked_query:
            response = self.client.get("/api/recognitions?limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json(), {
            "success": True,
            "recognitions": [{
                "log_id": 12,
                "subject_type": "member",
                "member_id": 3,
                "visitor_id": None,
                "name": "測試會員",
                "vip": True,
                "confidence": 0.92,
                "visit_time": "2026-07-29T10:30:45",
                "stay_minutes": 1.5,
            }],
            "count": 1,
            "limit": 10,
        })
        mocked_query.assert_called_once_with(limit=10)
        self.assertNotIn(
            "line_user_id",
            response.get_json()["recognitions"][0],
        )

    def test_uses_default_limit(self):
        with patch(
            "routes.camera.get_recognition_logs",
            return_value=[],
        ) as mocked_query:
            response = self.client.get("/api/recognitions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["limit"], 20)
        mocked_query.assert_called_once_with(limit=20)

    def test_rejects_non_integer_limit(self):
        response = self.client.get("/api/recognitions?limit=abc")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "success": False,
            "message": "limit 必須是整數",
        })

    def test_rejects_limit_outside_allowed_range(self):
        response = self.client.get("/api/recognitions?limit=101")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "success": False,
            "message": "limit 必須介於 1 到 100",
        })

    def test_returns_safe_error_when_database_query_fails(self):
        with patch(
            "routes.camera.get_recognition_logs",
            side_effect=RuntimeError("database details"),
        ):
            response = self.client.get("/api/recognitions")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {
            "success": False,
            "message": "無法取得辨識紀錄",
        })


if __name__ == "__main__":
    unittest.main()
