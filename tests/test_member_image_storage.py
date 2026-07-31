import inspect
import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from routes import line, member
from services import face_service, image_storage


class FakeBlob:
    def __init__(self):
        self.uploads = []
        self.deleted = False
        self.content_type = "image/jpeg"

    def upload_from_filename(self, path, **kwargs):
        self.uploads.append((path, kwargs))

    def delete(self):
        self.deleted = True


class FakeBucket:
    def __init__(self, blob):
        self._blob = blob

    def blob(self, object_name):
        self.object_name = object_name
        return self._blob


class FakeStorageClient:
    def __init__(self, blob):
        self._bucket = FakeBucket(blob)

    def bucket(self, bucket_name):
        self.bucket_name = bucket_name
        return self._bucket


class MemberImageStorageTests(unittest.TestCase):
    def test_parse_gcs_uri(self):
        self.assertEqual(
            ("photo-bucket", "member_images/a.jpg"),
            image_storage.parse_gcs_uri(
                "gs://photo-bucket/member_images/a.jpg"
            ),
        )

    def test_persist_member_image_uploads_to_configured_bucket(self):
        fake_blob = FakeBlob()
        fake_client = FakeStorageClient(fake_blob)

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image_file:
            with (
                patch.object(
                    image_storage,
                    "MEMBER_IMAGE_BUCKET",
                    "photo-bucket",
                ),
                patch.object(
                    image_storage,
                    "MEMBER_IMAGE_PREFIX",
                    "member_images",
                ),
                patch.object(
                    image_storage,
                    "_get_storage_client",
                    return_value=fake_client,
                ),
            ):
                result = image_storage.persist_member_image(
                    image_file.name,
                    "member.jpg",
                    content_type="image/jpeg",
                )

        self.assertEqual(
            "gs://photo-bucket/member_images/member.jpg",
            result,
        )
        self.assertEqual(
            "member_images/member.jpg",
            fake_client._bucket.object_name,
        )
        self.assertEqual(1, len(fake_blob.uploads))

    def test_delete_local_image_only_inside_allowed_root(self):
        with tempfile.TemporaryDirectory() as allowed_root:
            image_path = os.path.join(allowed_root, "member.jpg")
            with open(image_path, "wb") as image_file:
                image_file.write(b"image")

            deleted = image_storage.delete_member_image(
                image_path,
                local_roots=(allowed_root,),
            )

            self.assertTrue(deleted)
            self.assertFalse(os.path.exists(image_path))

    def test_delete_legacy_member_url_from_local_storage(self):
        with tempfile.TemporaryDirectory() as allowed_root:
            image_path = os.path.join(allowed_root, "line_member.jpg")
            with open(image_path, "wb") as image_file:
                image_file.write(b"line-registration-photo")

            deleted = image_storage.delete_member_image(
                (
                    "https://service.run.app/member_images/"
                    "line_member.jpg"
                ),
                local_roots=(allowed_root,),
            )

            self.assertTrue(deleted)
            self.assertFalse(os.path.exists(image_path))

    def test_member_photo_falls_back_to_existing_visitor_image(self):
        app = Flask(__name__)
        app.register_blueprint(member.member_bp)

        with tempfile.TemporaryDirectory() as visitor_dir:
            image_path = os.path.join(visitor_dir, "visitor.jpg")
            with open(image_path, "wb") as image_file:
                image_file.write(b"visitor-photo")

            with (
                patch.object(
                    member,
                    "VISITOR_IMAGE_DIR",
                    visitor_dir,
                ),
                patch.object(
                    member,
                    "_get_member_detail",
                    return_value={
                        "member_id": 13,
                        "face_image": (
                            "https://example.invalid/missing.jpg"
                        ),
                    },
                ),
                patch.object(
                    member,
                    "_get_member_image_paths",
                    return_value=[image_path],
                ),
            ):
                response = app.test_client().get(
                    "/member/13/photo"
                )

        self.assertEqual(200, response.status_code)
        self.assertEqual(b"visitor-photo", response.data)

    def test_line_registration_photo_is_preferred_over_visitor(self):
        app = Flask(__name__)
        app.register_blueprint(member.member_bp)
        line_photo = (
            "https://example.run.app/member_images/"
            "line_registration.jpg"
        )

        with (
            patch.object(
                member,
                "_get_member_detail",
                return_value={
                    "member_id": 14,
                    "face_image": line_photo,
                },
            ),
            patch.object(
                member,
                "_get_member_image_paths",
                return_value=["C:/visitor_images/camera.jpg"],
            ),
        ):
            response = app.test_client().get(
                "/member/14/photo"
            )

        self.assertEqual(302, response.status_code)
        self.assertEqual(line_photo, response.location)

    def test_member_delete_flow_includes_storage_cleanup(self):
        source = inspect.getsource(member.delete_member)
        self.assertIn("delete_member_image(", source)
        self.assertIn("SELECT face_image", source)

    def test_all_member_upload_flows_use_persistent_storage(self):
        add_source = inspect.getsource(member.add_member_page)
        edit_source = inspect.getsource(member.edit_member)
        line_source = inspect.getsource(line.register_from_line)

        self.assertIn("persist_member_image(", add_source)
        self.assertIn("persist_member_image(", edit_source)
        self.assertIn("persist_member_image(", line_source)
        self.assertIn("image_path=stored_image_path", line_source)

    def test_cloud_image_is_valid_for_duplicate_face_check(self):
        self.assertTrue(
            face_service.is_member_registration_face({
                "image_path": (
                    "gs://photo-bucket/member_images/member.jpg"
                ),
            })
        )

    def test_member_edit_preserves_identity_fields(self):
        edit_source = inspect.getsource(member.edit_member)
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
            "member_detail.html",
        )
        with open(
            template_path,
            "r",
            encoding="utf-8",
        ) as template_file:
            template_source = template_file.read()

        self.assertIn(
            'target_member.get("line_user_id")',
            edit_source,
        )
        self.assertIn(
            'target_member.get("total_amount")',
            edit_source,
        )
        self.assertIn('name="line_user_id"', template_source)
        self.assertIn("readonly", template_source)
        self.assertIn('name="total_amount"', template_source)


if __name__ == "__main__":
    unittest.main()
