import unittest
from unittest.mock import patch

from linebot_service import notify


class PreferencePromoTests(unittest.TestCase):
    def test_pushes_llm_recommendation_to_member(self):
        member = {
            "name": "王小明",
            "line_user_id": "U-member",
        }

        with patch.object(
            notify,
            "generate_preference_recommendation",
            return_value="王小明您好，歡迎到家具與燈飾區逛逛！",
        ) as generate, patch.object(
            notify,
            "push_message",
            return_value="sent",
        ) as push:
            result = notify.notify_preference_promo(
                member,
                preferences=["家具", "燈飾"],
            )

        self.assertEqual("sent", result)
        generate.assert_called_once_with("王小明", ["家具", "燈飾"])
        push.assert_called_once_with(
            "U-member",
            "王小明您好，歡迎到家具與燈飾區逛逛！",
        )

    def test_uses_existing_template_when_llm_is_unavailable(self):
        member = {
            "name": "王小明",
            "line_user_id": "U-member",
        }

        with patch.object(
            notify,
            "generate_preference_recommendation",
            return_value=None,
        ), patch.object(
            notify,
            "push_message",
            return_value="sent",
        ) as push:
            result = notify.notify_preference_promo(
                member,
                preferences=["家具"],
            )

        self.assertEqual("sent", result)
        self.assertIn("家具區", push.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
