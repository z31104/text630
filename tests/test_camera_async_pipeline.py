import inspect
import unittest
from unittest.mock import patch

import numpy as np

from routes import camera


class CameraAsyncPipelineTests(unittest.TestCase):
    def test_stream_does_not_run_ai_inference_inline(self):
        source = inspect.getsource(camera.generate_frames)

        self.assertIn("camera_ai_executor.submit(", source)
        self.assertIn("queue_member_visit_update(", source)
        self.assertIn("visitor_conversion_executor.submit(", source)
        self.assertNotIn("detect_face(frame)", source)
        self.assertNotIn("recognize_face(", source)
        self.assertNotIn("register_new_visitor(", source)

    def test_background_analysis_returns_faces_and_result(self):
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        faces = [(1, 2, 10, 10)]
        expected_result = {
            "recognition_status": "recognized",
            "member_id": 3,
        }

        with (
            patch.object(
                camera,
                "detect_face",
                return_value=faces,
            ),
            patch.object(
                camera,
                "process_camera_recognition",
                return_value=expected_result,
            ),
        ):
            result = camera.analyze_camera_frame(
                frame,
                perform_recognition=True,
            )

        self.assertEqual(faces, result["faces"])
        self.assertEqual(expected_result, result["result"])

    def test_detection_only_round_skips_full_recognition(self):
        frame = np.zeros((20, 20, 3), dtype=np.uint8)

        with (
            patch.object(
                camera,
                "detect_face",
                return_value=[],
            ),
            patch.object(
                camera,
                "process_camera_recognition",
            ) as recognize_mock,
        ):
            result = camera.analyze_camera_frame(
                frame,
                perform_recognition=False,
            )

        recognize_mock.assert_not_called()
        self.assertEqual([], result["faces"])
        self.assertIsNone(result["result"])

    def test_cross_process_conversion_returns_current_member(self):
        with (
            patch.object(
                camera,
                "get_visitor_by_id",
                return_value={
                    "visitor_id": 7,
                    "converted_member_id": 42,
                },
            ),
            patch.object(
                camera,
                "get_member_by_id",
                return_value={
                    "member_id": 42,
                    "name": "新會員",
                    "vip": True,
                    "member_level": "vip",
                },
            ),
            patch.object(
                camera,
                "get_active_visit",
                return_value={"log_id": 88},
            ),
        ):
            result = camera.check_visitor_conversion(7)

        self.assertEqual(7, result["visitor_id"])
        self.assertEqual(42, result["member"]["member_id"])
        self.assertEqual(88, result["converted_active_log_id"])

    def test_face_caches_refresh_independently(self):
        with (
            patch.object(
                camera,
                "reload_member_faces",
                side_effect=RuntimeError("member database unavailable"),
            ) as reload_members,
            patch.object(
                camera,
                "reload_visitor_faces",
                return_value=[{"visitor_id": 8}],
            ) as reload_visitors,
        ):
            result = camera.refresh_face_caches_once()

        reload_members.assert_called_once_with(strict=True)
        reload_visitors.assert_called_once_with(strict=True)
        self.assertEqual(
            "member database unavailable",
            result["會員"]["error"],
        )
        self.assertEqual(1, result["散客"]["count"])
        self.assertIsNone(result["散客"]["error"])

    def test_timeout_check_is_dispatched_to_background_executor(self):
        source = inspect.getsource(camera.generate_frames)

        self.assertIn(
            "visit_db_executor.submit(\n"
            "                    close_timeout_visits,",
            source,
        )


if __name__ == "__main__":
    unittest.main()
