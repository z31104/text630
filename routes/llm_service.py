import os

import requests


_DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen3.5-flash"
_EMPTY_MESSAGE = "請輸入想詢問的問題。"
_UNAVAILABLE_MESSAGE = "目前智慧客服暫時無法使用，請稍後再試。"
_REQUEST_TIMEOUT = (3.05, 15)

_SYSTEM_PROMPT = """你是智慧會員系統的 LINE 客服助理。
請使用繁體中文，以簡短、清楚、容易理解的方式回答。
每次回答控制在 2～4 句，不要長篇解釋。
主要回答會員註冊、優惠券、抽獎、VIP、到店紀錄等基本問題。
如果無法確定實際會員狀態、優惠券期限或系統資料，不可自行捏造，請提醒使用者確認登入帳號、使用條件，或聯絡店家人員協助。"""


def _extract_answer(response_data: object) -> str | None:
    if not isinstance(response_data, dict):
        return None

    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None

    return content.strip()


def ask_llm(user_message: str) -> str:
    """回覆單次會員系統客服問題，不保存對話紀錄。"""
    if not isinstance(user_message, str) or not user_message.strip():
        return _EMPTY_MESSAGE

    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return _UNAVAILABLE_MESSAGE

    base_url = (
        os.getenv("LLM_BASE_URL", "").strip()
        or _DEFAULT_BASE_URL
    ).rstrip("/")
    model = os.getenv("LLM_MODEL", "").strip() or _DEFAULT_MODEL

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message.strip()},
                ],
                "max_completion_tokens": 200,
                "enable_thinking": False,
                "stream": False,
            },
            timeout=_REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
        answer = _extract_answer(response.json())
    except (requests.RequestException, ValueError):
        return _UNAVAILABLE_MESSAGE

    return answer or _UNAVAILABLE_MESSAGE
