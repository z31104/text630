import unittest
from unittest.mock import patch

from app import app
from services import face_service


class ReloadFacesApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_reload_faces_returns_loaded_face_counts(self):
        members = [
            {"member_id": 1},
            {"member_id": 1},
            {"member_id": 2},
        ]
        visitors = [{"visitor_id": 8}]

        with patch(
            "routes.camera.reload_all_faces",
            return_value=(members, visitors),
        ) as mocked_reload:
            response = self.client.post("/camera/reload-faces")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json(), {
            "success": True,
            "message": "Face data reloaded successfully.",
            "member_count": 3,
            "visitor_count": 1,
        })
        mocked_reload.assert_called_once_with()

    def test_reload_faces_returns_safe_error(self):
        with patch(
            "routes.camera.reload_all_faces",
            side_effect=RuntimeError(
                "database password and internal details",
            ),
        ):
            response = self.client.post("/camera/reload-faces")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {
            "success": False,
            "message": "Face data reload failed.",
        })
        self.assertNotIn(
            "database password",
            response.get_data(as_text=True),
        )

    def test_reload_faces_rejects_get_requests(self):
        response = self.client.get("/camera/reload-faces")

        self.assertEqual(response.status_code, 405)

    def test_reload_all_faces_keeps_old_cache_on_failure(self):
        original_members = list(face_service.known_members)
        original_visitors = list(face_service.known_visitors)

        old_members = [{"member_id": 10}]
        old_visitors = [{"visitor_id": 20}]

        try:
            with face_service.face_cache_lock:
                face_service.known_members[:] = old_members
                face_service.known_visitors[:] = old_visitors

            with (
                patch(
                    "services.face_service.load_member_faces",
                    return_value=[{"member_id": 99}],
                ),
                patch(
                    "services.face_service.load_visitor_faces",
                    return_value=None,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "散客人臉資料載入失敗",
                ):
                    face_service.reload_all_faces()

            self.assertEqual(face_service.known_members, old_members)
            self.assertEqual(face_service.known_visitors, old_visitors)
        finally:
            with face_service.face_cache_lock:
                face_service.known_members[:] = original_members
                face_service.known_visitors[:] = original_visitors


if __name__ == "__main__":
    unittest.main()
