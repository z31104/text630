import os
import unittest
from unittest.mock import Mock, patch

import requests

from routes import llm_service


class LlmServiceTests(unittest.TestCase):
    def test_empty_message_does_not_call_api(self):
        with patch.object(llm_service.requests, "post") as mocked_post:
            answer = llm_service.ask_llm("   ")

        self.assertEqual("請輸入想詢問的問題。", answer)
        mocked_post.assert_not_called()

    def test_missing_api_key_returns_unavailable_message(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            llm_service.requests,
            "post",
        ) as mocked_post:
            answer = llm_service.ask_llm("如何註冊會員？")

        self.assertEqual("目前智慧客服暫時無法使用，請稍後再試。", answer)
        mocked_post.assert_not_called()

    def test_successful_response_returns_qwen_answer(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{
                "message": {"content": "請點選選單中的會員註冊。"},
            }],
        }

        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "test-key",
                "LLM_BASE_URL": "https://llm.example/v1/",
                "LLM_MODEL": "test-model",
            },
            clear=True,
        ), patch.object(
            llm_service.requests,
            "post",
            return_value=response,
        ) as mocked_post:
            answer = llm_service.ask_llm("  如何註冊會員？  ")

        self.assertEqual("請點選選單中的會員註冊。", answer)
        request = mocked_post.call_args
        self.assertEqual(
            "https://llm.example/v1/chat/completions",
            request.args[0],
        )
        self.assertEqual("Bearer test-key", request.kwargs["headers"]["Authorization"])
        self.assertEqual("test-model", request.kwargs["json"]["model"])
        self.assertEqual(
            "如何註冊會員？",
            request.kwargs["json"]["messages"][1]["content"],
        )
        self.assertEqual((3.05, 15), request.kwargs["timeout"])

    def test_request_failure_returns_unavailable_message(self):
        with patch.dict(
            os.environ,
            {"LLM_API_KEY": "test-key"},
            clear=True,
        ), patch.object(
            llm_service.requests,
            "post",
            side_effect=requests.Timeout("timeout"),
        ):
            answer = llm_service.ask_llm("優惠券怎麼使用？")

        self.assertEqual("目前智慧客服暫時無法使用，請稍後再試。", answer)

    def test_malformed_response_returns_unavailable_message(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": []}

        with patch.dict(
            os.environ,
            {"LLM_API_KEY": "test-key"},
            clear=True,
        ), patch.object(
            llm_service.requests,
            "post",
            return_value=response,
        ):
            answer = llm_service.ask_llm("VIP 有什麼優惠？")

        self.assertEqual("目前智慧客服暫時無法使用，請稍後再試。", answer)

    def test_preference_recommendation_uses_all_registered_preferences(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{
                "message": {"content": "王小明您好，歡迎到家具與燈飾區逛逛！"},
            }],
        }

        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "test-key",
                "LLM_BASE_URL": "https://llm.example/v1/",
                "LLM_MODEL": "test-model",
            },
            clear=True,
        ), patch.object(
            llm_service.requests,
            "post",
            return_value=response,
        ) as mocked_post:
            answer = llm_service.generate_preference_recommendation(
                "王小明",
                ["家具", "燈飾"],
            )

        self.assertEqual("王小明您好，歡迎到家具與燈飾區逛逛！", answer)
        prompt = mocked_post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("王小明", prompt)
        self.assertIn("家具、燈飾", prompt)
        self.assertNotIn("line_user_id", prompt)
        self.assertEqual(120, mocked_post.call_args.kwargs["json"]["max_completion_tokens"])

    def test_preference_recommendation_without_api_key_uses_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            llm_service.requests,
            "post",
        ) as mocked_post:
            answer = llm_service.generate_preference_recommendation(
                "王小明",
                ["家具"],
            )

        self.assertIsNone(answer)
        mocked_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
