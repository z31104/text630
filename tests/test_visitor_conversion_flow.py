from io import BytesIO
import tempfile
import threading
import unittest
from unittest.mock import patch

from app import app
from database import db
from routes import camera
from routes import member


class FakeCursor:
    def __init__(self, active_log_id, stale_log=False):
        self.active_log_id = active_log_id
        self.stale_log = stale_log
        self.lastrowid = 42
        self.rowcount = 0
        self._fetchone = None
        self.executed = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params))

        if "FROM visitors" in normalized and "FOR UPDATE" in normalized:
            self._fetchone = {
                "visitor_id": 7,
                "visitor_code": "V-ORIGINAL-CODE",
                "converted_member_id": None,
                "visitor_visit_count": 1,
                "last_seen_at": "2026-07-28 10:00:00",
            }
        elif normalized.startswith("INSERT INTO members"):
            self.rowcount = 1
        elif normalized.startswith("INSERT INTO face_images"):
            self.rowcount = 1
        elif normalized.startswith("UPDATE visitors"):
            self.rowcount = 1
        elif (
            normalized.startswith("SELECT log_id, visit_time")
            and "DATE_SUB" in normalized
        ):
            self._fetchone = (
                {
                    "log_id": self.active_log_id,
                    "visit_time": "2026-07-28 10:00:00",
                    "recognized_at": "2026-07-28 10:00:00",
                    "last_seen_at": "2026-07-28 10:00:05",
                }
                if self.stale_log and self.active_log_id is not None
                else None
            )
        elif normalized.startswith("SELECT log_id"):
            self._fetchone = (
                {"log_id": self.active_log_id}
                if self.active_log_id is not None and not self.stale_log
                else None
            )
        elif normalized.startswith("UPDATE recognition_logs"):
            self.rowcount = 1

    def fetchone(self):
        return self._fetchone

    def close(self):
        pass


class FakeConnection:
    def __init__(self, active_log_id, stale_log=False):
        self.cursor_instance = FakeCursor(active_log_id, stale_log)
        self.committed = False
        self.rolled_back = False

    def cursor(self, dictionary=False):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class VisitorConversionDatabaseTests(unittest.TestCase):
    def run_conversion(self, active_log_id, stale_log=False):
        connection = FakeConnection(active_log_id, stale_log)
        with patch.object(db, "get_connection", return_value=connection):
            result = db.convert_visitor_to_member(
                visitor_id=7,
                name="測試會員",
            )
        return connection, result

    def test_closed_visit_history_is_not_rewritten(self):
        connection, result = self.run_conversion(active_log_id=None)
        updates = [
            sql for sql, _ in connection.cursor_instance.executed
            if sql.startswith("UPDATE recognition_logs")
        ]

        self.assertEqual([], updates)
        self.assertIsNone(result["converted_active_log_id"])
        self.assertTrue(connection.committed)

    def test_active_visit_reuses_original_log_id(self):
        connection, result = self.run_conversion(active_log_id=88)
        updates = [
            (sql, params)
            for sql, params in connection.cursor_instance.executed
            if sql.startswith("UPDATE recognition_logs")
        ]

        self.assertEqual(1, len(updates))
        self.assertEqual(88, updates[0][1][-1])
        self.assertNotIn("visitor_id = %s", updates[0][0])
        self.assertEqual(88, result["converted_active_log_id"])

    def test_stale_active_visit_is_closed_as_visitor_history(self):
        connection, result = self.run_conversion(
            active_log_id=77,
            stale_log=True,
        )
        updates = [
            (sql, params)
            for sql, params in connection.cursor_instance.executed
            if sql.startswith("UPDATE recognition_logs")
        ]

        self.assertEqual(1, len(updates))
        self.assertIn("visit_status = 'left'", updates[0][0])
        self.assertEqual(77, updates[0][1][-1])
        self.assertIsNone(result["converted_active_log_id"])
        self.assertEqual(77, result["closed_stale_log_id"])


class VisitorConversionCacheTests(unittest.TestCase):
    def setUp(self):
        self.original_active_visits = camera.active_visits
        self.original_lock = camera.active_visits_lock
        self.original_last_result = camera.last_result
        self.original_last_recognition_time = camera.last_recognition_time
        camera.active_visits = {}
        camera.active_visits_lock = threading.Lock()
        camera.last_result = {}
        camera.last_recognition_time = 123

    def tearDown(self):
        camera.active_visits = self.original_active_visits
        camera.active_visits_lock = self.original_lock
        camera.last_result = self.original_last_result
        camera.last_recognition_time = self.original_last_recognition_time

    def test_active_visit_moves_to_member_key_without_new_log(self):
        camera.active_visits["visitor:7"] = {
            "log_id": 88,
            "visit_time": "2026-07-28 10:00:00",
            "result": {
                "subject_type": "visitor",
                "visitor_id": 7,
                "visitor_code": "V-ORIGINAL-CODE",
            },
        }
        camera.last_result = dict(
            camera.active_visits["visitor:7"]["result"]
        )

        converted = camera.convert_visitor_active_visit(
            visitor_id=7,
            member_id=42,
            name="測試會員",
            converted_active_log_id=88,
        )

        self.assertTrue(converted)
        self.assertNotIn("visitor:7", camera.active_visits)
        self.assertIn("member:42", camera.active_visits)
        visit = camera.active_visits["member:42"]
        self.assertEqual(88, visit["log_id"])
        self.assertEqual(88, visit["result"]["log_id"])
        self.assertEqual(7, visit["result"]["visitor_id"])
        self.assertEqual("V-ORIGINAL-CODE", visit["result"]["visitor_code"])
        self.assertEqual("member", camera.last_result["subject_type"])

    def test_closed_visit_is_cleared_for_next_member_entry(self):
        camera.active_visits["visitor:7"] = {
            "log_id": 77,
            "result": {"subject_type": "visitor", "visitor_id": 7},
        }
        camera.last_result = {"subject_type": "visitor", "visitor_id": 7}

        converted = camera.convert_visitor_active_visit(
            visitor_id=7,
            member_id=42,
            name="測試會員",
            converted_active_log_id=None,
        )

        self.assertFalse(converted)
        self.assertEqual({}, camera.active_visits)
        self.assertEqual({}, camera.last_result)
        self.assertEqual(0, camera.last_recognition_time)


class BackendRegistrationConversionTests(unittest.TestCase):
    def test_backend_registration_uses_visitor_conversion(self):
        encoding = [0.0] * 128

        with tempfile.TemporaryDirectory() as image_dir, patch.object(
            member,
            "MEMBER_IMAGE_DIR",
            image_dir,
        ), patch.object(
            member,
            "validate_member_face_image",
            return_value={"success": True, "encoding": encoding},
        ), patch.object(
            member,
            "find_matching_visitor",
            return_value={
                "matched": True,
                "visitor_id": 7,
                "visitor_code": "V-ORIGINAL-CODE",
            },
        ), patch.object(
            member,
            "convert_visitor_to_member",
            return_value={
                "member_id": 42,
                "converted_active_log_id": 88,
            },
        ) as convert_mock, patch.object(
            member,
            "register_member_with_face",
        ) as new_member_mock, patch.object(
            member,
            "reload_member_faces",
        ), patch.object(
            member,
            "reload_visitor_faces",
        ), patch.object(
            member,
            "sync_converted_visitor_cache",
        ), patch.object(
            camera,
            "convert_visitor_active_visit",
        ) as active_visit_mock:
            app.config["TESTING"] = True
            with app.test_client() as client:
                response = client.post(
                    "/member/add",
                    data={
                        "name": "測試會員",
                        "vip": "1",
                        "face_image": (
                            BytesIO(b"fake-image"),
                            "face.jpg",
                        ),
                    },
                    content_type="multipart/form-data",
                )

        self.assertEqual(302, response.status_code)
        new_member_mock.assert_not_called()
        self.assertEqual(
            "backend_visitor_conversion",
            convert_mock.call_args.kwargs["registration_source"],
        )
        self.assertEqual(
            88,
            active_visit_mock.call_args.kwargs[
                "converted_active_log_id"
            ],
        )


if __name__ == "__main__":
    unittest.main()
