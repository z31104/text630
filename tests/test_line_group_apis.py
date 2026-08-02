import unittest
from unittest.mock import patch

from app import app
from routes import line as line_module


class LineGroupApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    # ---------- API 1: LINE Register ----------

    def test_register_missing_name(self):
        response = self.client.post(
            "/line/register",
            data={"line_user_id": "Utest123"},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "請輸入姓名",
            response.get_json()["message"],
        )

    def test_register_missing_line_user_id(self):
        response = self.client.post(
            "/line/register",
            data={"name": "測試員"},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "缺少 LINE 使用者資訊，請從 LINE 官方帳號的註冊連結進入此頁面",
            response.get_json()["message"],
        )

    # ---------- API 2: VIP Notify ----------

    def test_notify_vip_success(self):
        with patch.object(
            line_module,
            "notify_vip_recognition",
            return_value="sent",
        ) as mock_notify:
            response = self.client.post(
                "/api/notify/vip",
                json={"member_id": 1},
            )

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertTrue(body["notified"])
        self.assertEqual("sent", body["status"])
        mock_notify.assert_called_once()

    def test_notify_vip_non_vip_member_skips_push(self):
        with patch.object(
            line_module,
            "notify_vip_recognition",
        ) as mock_notify:
            response = self.client.post(
                "/api/notify/vip",
                json={"member_id": 2},
            )

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertFalse(body["notified"])
        mock_notify.assert_not_called()

    def test_notify_vip_missing_member_id(self):
        response = self.client.post("/api/notify/vip", json={})
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "缺少 member_id",
            response.get_json()["message"],
        )

    def test_notify_vip_member_not_found(self):
        response = self.client.post(
            "/api/notify/vip",
            json={"member_id": 99999},
        )
        self.assertEqual(404, response.status_code)
        self.assertEqual(
            "找不到這位會員",
            response.get_json()["message"],
        )

    # ---------- API 3: Coupon（member_id 內部查詢端點） ----------

    def test_coupons_by_member_id_has_data(self):
        response = self.client.get("/api/member/2/coupons")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertGreaterEqual(body["count"], 1)
        coupon = body["data"][0]
        self.assertIn("member_coupon_id", coupon)
        self.assertIn("T", coupon["receive_time"])

    def test_coupons_by_member_id_empty(self):
        response = self.client.get("/api/member/8/coupons")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(0, body["count"])
        self.assertEqual([], body["data"])

    # ---------- API 4: Lottery Draw ----------

    def test_lottery_draw_already_completed(self):
        with patch.object(
            line_module,
            "notify_lottery_result",
        ) as mock_notify:
            response = self.client.post(
                "/api/lottery/draw",
                json={"member_id": 2},
            )

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertTrue(body["already_completed"])
        self.assertEqual(
            "WELCOME_FREE_SHIP",
            body["prize"]["prize_code"],
        )
        mock_notify.assert_called_once()

    def test_lottery_draw_missing_member_id(self):
        response = self.client.post("/api/lottery/draw", json={})
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "缺少 member_id",
            response.get_json()["message"],
        )

    # ---------- API 5: Lottery Result ----------

    def test_lottery_result_has_result(self):
        response = self.client.get("/api/lottery/result/2")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["has_result"])
        self.assertEqual(
            "WELCOME_FREE_SHIP",
            body["data"]["prize_code"],
        )

    def test_lottery_result_no_result(self):
        response = self.client.get("/api/lottery/result/8")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertFalse(body["has_result"])
        self.assertIsNone(body["data"])

    # ---------- 額外端點：Coupons Me ----------

    def test_coupons_me_missing_token(self):
        response = self.client.post("/api/coupons/me", json={})
        self.assertEqual(401, response.status_code)
        self.assertEqual(
            "缺少 LINE 登入憑證，請從 LINE 官方帳號重新開啟頁面",
            response.get_json()["message"],
        )

    def test_coupons_me_invalid_token(self):
        class _FakeResponse:
            status_code = 400
            text = '{"error":"invalid_request"}'

        with patch.object(
            line_module.requests,
            "post",
            return_value=_FakeResponse(),
        ):
            response = self.client.post(
                "/api/coupons/me",
                json={"id_token": "fake-token"},
            )

        self.assertEqual(401, response.status_code)
        self.assertEqual(
            "LINE 登入已過期或無效，請重新登入後再試",
            response.get_json()["message"],
        )


if __name__ == "__main__":
    unittest.main()
