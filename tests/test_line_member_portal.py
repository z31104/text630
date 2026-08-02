import os
import unittest
from unittest.mock import patch


class LineMemberPortalTests(unittest.TestCase):
    def test_member_portal_redirects_through_liff(self):
        liff_id = "1234567890-testApp"

        with patch.dict(
            os.environ,
            {
                "LIFF_ID_COUPONS": liff_id,
                "LINE_CHANNEL_ACCESS_TOKEN": "",
                "LINE_CHANNEL_SECRET": "",
            },
        ):
            from importlib import reload
            from routes import line

            reload(line)

            from flask import Flask

            app = Flask(__name__)
            app.register_blueprint(line.line_bp)

            response = app.test_client().get("/member-area")

        self.assertEqual(302, response.status_code)
        self.assertEqual(
            f"https://liff.line.me/{liff_id}",
            response.headers["Location"],
        )

    def test_coupon_reauthentication_uses_liff_and_callback_uses_endpoint(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        script_path = os.path.join(
            project_root,
            "static",
            "js",
            "coupons.js",
        )

        with open(script_path, encoding="utf-8") as script_file:
            source = script_file.read()

        liff_url = "https://liff.line.me/${LIFF_ID_COUPONS}"
        self.assertIn(liff_url, source)
        self.assertIn("liff.login();", source)
        self.assertNotIn("redirectUri:", source)

    def test_member_coupon_api_falls_back_for_legacy_prize_schema(self):
        from flask import Flask
        from routes import line

        app = Flask(__name__)
        app.register_blueprint(line.line_bp)
        legacy_schema_error = Exception(
            "1054 (42S22): Unknown column "
            "'mp.member_coupon_id' in 'on clause'"
        )

        with (
            patch.object(
                line,
                "_decode_line_id_token",
                return_value=("U-member", None),
            ),
            patch.object(
                line,
                "_fetch_member_by_line_user_id",
                return_value={"member_id": 7},
            ),
            patch.object(
                line,
                "get_member_coupons",
                side_effect=legacy_schema_error,
            ),
            patch.object(
                line,
                "_fetch_member_coupons_without_redemption",
                return_value=[],
            ) as fallback,
        ):
            response = app.test_client().post(
                "/api/coupons/me",
                json={"id_token": "valid-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["bound"])
        fallback.assert_called_once_with(member_id=7, limit=500)


if __name__ == "__main__":
    unittest.main()
