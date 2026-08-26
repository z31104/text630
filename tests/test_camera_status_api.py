import unittest
from unittest.mock import patch

from app import app
from routes import camera
from services import face_service


class CameraStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_camera_status_api_returns_required_fields(self):
        with camera.camera_status_lock:
            original_status = dict(camera.camera_status)
            camera.camera_status.update({
                "connected": True,
                "status": "Connected",
                "message": "攝影機連線正常",
            })

        try:
            with patch(
                "routes.camera.get_face_service_status",
                return_value={
                    "ai_operational": True,
                    "loaded_member_count": 2,
                    "loaded_visitor_count": 3,
                },
            ):
                response = self.client.get("/api/camera/status")
        finally:
            with camera.camera_status_lock:
                camera.camera_status.clear()
                camera.camera_status.update(original_status)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json(), {
            "success": True,
            "camera_connected": True,
            "camera_status": "Connected",
            "camera_message": "攝影機連線正常",
            "ai_operational": True,
            "loaded_member_count": 2,
            "loaded_visitor_count": 3,
        })

    def test_face_service_status_counts_unique_people(self):
        original_members = list(face_service.known_members)
        original_visitors = list(face_service.known_visitors)

        try:
            with face_service.face_cache_lock:
                face_service.known_members[:] = [
                    {"member_id": 1},
                    {"member_id": 1},
                    {"member_id": 2},
                    {"member_id": None},
                ]
                face_service.known_visitors[:] = [
                    {"visitor_id": 8},
                    {"visitor_id": 8},
                    {"visitor_id": 9},
                ]

            with patch(
                "services.face_service._get_face_recognition",
                return_value=object(),
            ):
                status = face_service.get_face_service_status()
        finally:
            with face_service.face_cache_lock:
                face_service.known_members[:] = original_members
                face_service.known_visitors[:] = original_visitors

        self.assertTrue(status["ai_operational"])
        self.assertEqual(status["loaded_member_count"], 2)
        self.assertEqual(status["loaded_visitor_count"], 2)


if __name__ == "__main__":
    unittest.main()
