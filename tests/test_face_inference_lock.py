import ast
import threading
import time
import unittest
from pathlib import Path

from services import face_service


class _ConcurrentFaceRecognition:
    def __init__(self):
        self.state_lock = threading.Lock()
        self.active_calls = 0
        self.max_active_calls = 0

    def _run(self):
        with self.state_lock:
            self.active_calls += 1
            self.max_active_calls = max(
                self.max_active_calls,
                self.active_calls,
            )

        time.sleep(0.05)

        with self.state_lock:
            self.active_calls -= 1

        return []

    def face_locations(self, *args, **kwargs):
        return self._run()

    def face_encodings(self, *args, **kwargs):
        return self._run()


class FaceInferenceLockTests(unittest.TestCase):
    def test_different_inference_calls_are_serialized(self):
        original = face_service.face_recognition
        fake = _ConcurrentFaceRecognition()
        start = threading.Event()

        def call_locations():
            start.wait()
            face_service._locked_face_locations(object())

        def call_encodings():
            start.wait()
            face_service._locked_face_encodings(object())

        face_service.face_recognition = fake
        try:
            threads = [
                threading.Thread(target=call_locations),
                threading.Thread(target=call_encodings),
            ]
            for thread in threads:
                thread.start()

            start.set()

            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
        finally:
            face_service.face_recognition = original

        self.assertEqual(fake.max_active_calls, 1)

    def test_native_calls_only_exist_inside_lock_wrappers(self):
        source_path = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "face_service.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        direct_calls = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            if not isinstance(function.value, ast.Name):
                continue
            if function.value.id != "face_recognition":
                continue
            if function.attr not in {
                "face_locations",
                "face_encodings",
                "face_distance",
            }:
                continue
            direct_calls.append((function.attr, node.lineno))

        self.assertEqual(
            [name for name, _ in direct_calls],
            ["face_locations", "face_encodings", "face_distance"],
        )


if __name__ == "__main__":
    unittest.main()
