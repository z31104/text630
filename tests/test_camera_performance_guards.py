import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from routes import camera
from services import face_service


class CameraPerformanceGuardTests(unittest.TestCase):
    def tearDown(self):
        camera.reset_guest_confirmation()

    def test_stream_loop_does_not_reload_faces_from_database(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "routes"
            / "camera.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        generate_frames = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "generate_frames"
        )
        reload_calls = []

        for node in ast.walk(generate_frames):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name):
                continue
            if node.func.id in {
                "reload_all_faces",
                "reload_member_faces",
                "reload_visitor_faces",
            }:
                reload_calls.append(node.func.id)

        self.assertEqual([], reload_calls)

    def test_guest_must_be_stable_across_multiple_encodings(self):
        stable_encoding = np.zeros(128)
        moved_encoding = np.ones(128)

        with patch.object(camera, "GUEST_CONFIRM_REQUIRED", 3):
            self.assertFalse(camera.confirm_stable_guest({
                "_face_encoding": stable_encoding,
            }))
            self.assertFalse(camera.confirm_stable_guest({
                "_face_encoding": stable_encoding,
            }))
            self.assertFalse(camera.confirm_stable_guest({
                "_face_encoding": moved_encoding,
            }))
            self.assertFalse(camera.confirm_stable_guest({
                "_face_encoding": stable_encoding,
            }))
            self.assertFalse(camera.confirm_stable_guest({
                "_face_encoding": stable_encoding,
            }))
            self.assertTrue(camera.confirm_stable_guest({
                "_face_encoding": stable_encoding,
            }))

    def test_last_seen_update_is_queued(self):
        with patch.object(
            camera.visit_db_executor,
            "submit",
        ) as submit:
            queued = camera.queue_recognition_last_seen(
                12,
                "2026-07-30 18:00:00",
            )

        self.assertTrue(queued)
        submit.assert_called_once_with(
            camera.update_recognition_last_seen,
            12,
            "2026-07-30 18:00:00",
        )


class VisitorRegistrationGuardTests(unittest.TestCase):
    def test_existing_visitor_is_reused_before_insert(self):
        frame = np.random.default_rng(42).integers(
            0,
            256,
            size=(240, 240, 3),
            dtype=np.uint8,
        )
        encoding = np.zeros(128)
        existing = {
            "visitor_id": 6,
            "visitor_code": "V-EXISTING",
            "display_name": "V-EXISTING",
            "encoding": encoding,
        }
        original_visitors = list(face_service.known_visitors)

        try:
            with face_service.face_cache_lock:
                face_service.known_visitors[:] = [existing]

            with (
                patch.object(
                    face_service,
                    "_get_face_recognition",
                    return_value=Mock(),
                ),
                patch.object(
                    face_service,
                    "find_matching_visitor",
                    return_value={
                        "matched": True,
                        "visitor_id": 6,
                        "visitor_code": "V-EXISTING",
                        "confidence": 0.8,
                    },
                ),
                patch.object(
                    face_service,
                    "db_register_visitor_with_face",
                ) as insert_visitor,
            ):
                result = face_service.register_new_visitor(
                    frame,
                    [(70, 70, 100, 100)],
                    encoding=encoding,
                )

            self.assertEqual("visitor", result["subject_type"])
            self.assertEqual(6, result["visitor_id"])
            insert_visitor.assert_not_called()
        finally:
            with face_service.face_cache_lock:
                face_service.known_visitors[:] = original_visitors


if __name__ == "__main__":
    unittest.main()
