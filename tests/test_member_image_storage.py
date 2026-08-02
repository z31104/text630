import os
import unittest
from unittest.mock import MagicMock, patch

from services import member_image_storage


class MemberImageStorageTests(unittest.TestCase):
    def test_blob_name_removes_directories(self):
        with patch.object(member_image_storage, "OBJECT_PREFIX", "member_images"):
            self.assertEqual(
                member_image_storage._blob_name(r"C:\\tmp\\member.jpg"),
                "member_images/member.jpg",
            )

    def test_download_returns_none_without_bucket_configuration(self):
        with patch.object(member_image_storage, "BUCKET_NAME", ""):
            self.assertIsNone(member_image_storage.download_member_image("missing.jpg"))

    def test_upload_uses_expected_object_and_content_type(self):
        bucket = MagicMock()
        blob = bucket.blob.return_value
        with patch.object(member_image_storage, "_bucket", return_value=bucket):
            self.assertTrue(member_image_storage.upload_member_image("member_images/a.png"))
        bucket.blob.assert_called_once_with("member_images/a.png")
        blob.upload_from_filename.assert_called_once_with(
            "member_images/a.png",
            content_type="image/png",
        )


if __name__ == "__main__":
    unittest.main()
