import unittest
from unittest.mock import patch

from flask import Flask

from routes import coupon


class WelcomeCouponRedemptionTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(coupon.coupon_bp)
        self.client = app.test_client()

    def test_redeems_coupon_for_authenticated_member(self):
        with (
            patch.object(
                coupon,
                "_decode_line_id_token",
                return_value=("U-member", None),
            ),
            patch.object(
                coupon,
                "_fetch_member_by_line_user_id",
                return_value={"member_id": 25},
            ),
            patch.object(
                coupon,
                "redeem_member_coupon",
                return_value={
                    "success": True,
                    "message": "100 元折價券兌換成功",
                    "member_coupon_id": 88,
                },
            ) as redeem,
        ):
            response = self.client.post(
                "/api/coupons/88/redeem",
                json={"id_token": "valid-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["success"])
        redeem.assert_called_once_with(
            member_coupon_id=88,
            member_id=25,
        )

    def test_rejects_redemption_without_line_login(self):
        with patch.object(
            coupon,
            "_decode_line_access_token",
            return_value=(None, "缺少 LINE 登入憑證"),
        ), patch.object(coupon, "redeem_member_coupon") as redeem:
            response = self.client.post(
                "/api/coupons/88/redeem",
                json={},
            )

        self.assertEqual(401, response.status_code)
        redeem.assert_not_called()

    def test_returns_conflict_after_coupon_is_already_used(self):
        with (
            patch.object(
                coupon,
                "_decode_line_id_token",
                return_value=("U-member", None),
            ),
            patch.object(
                coupon,
                "_fetch_member_by_line_user_id",
                return_value={"member_id": 25},
            ),
            patch.object(
                coupon,
                "redeem_member_coupon",
                return_value={
                    "success": False,
                    "message": "這張優惠券已經兌換",
                },
            ),
        ):
            response = self.client.post(
                "/api/coupons/88/redeem",
                json={"id_token": "valid-token"},
            )

        self.assertEqual(409, response.status_code)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
