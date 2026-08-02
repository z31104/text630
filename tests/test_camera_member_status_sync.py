import unittest

from routes import camera
from services.visit_service import build_subject_key


class CameraMemberStatusSyncTests(unittest.TestCase):
    def setUp(self):
        self.original_active_visits = camera.active_visits.copy()
        self.original_last_result = camera.last_result.copy()
        camera.active_visits.clear()

    def tearDown(self):
        camera.active_visits.clear()
        camera.active_visits.update(self.original_active_visits)
        camera.last_result = self.original_last_result

    def test_refreshes_active_visit_and_last_result(self):
        key = build_subject_key(subject_type="member", member_id=7)
        camera.active_visits[key] = {
            "result": {"member_id": 7, "vip": False, "member_level": "normal"}
        }
        camera.last_result = {
            "subject_type": "member",
            "member_id": 7,
            "vip": False,
            "member_level": "normal",
        }

        updated = camera.refresh_active_member_status(
            member_id=7,
            name="VIP Test",
            vip=True,
            member_level="vip",
            line_user_id="U-test",
        )

        self.assertTrue(updated)
        self.assertTrue(camera.active_visits[key]["result"]["vip"])
        self.assertEqual("vip", camera.last_result["member_level"])
        self.assertEqual("VIP 會員", camera.last_result["member_level_text"])


if __name__ == "__main__":
    unittest.main()
