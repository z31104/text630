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
可以自然回應簡單寒暄（打招呼、道謝等）與基本數學計算，不必因為跟會員系統無關就拒答。
主要任務是回答會員註冊、優惠券、抽獎、VIP、到店紀錄等基本問題。
如果對話中有提供「目前使用者的會員資料」，代表這是系統查證過的真實資料，
請直接根據該資料回答，不要說自己查不到或無法查詢會員系統。
如果沒有提供會員資料，或使用者問的是會員系統相關但超出提供資料範圍的內容，
不可自行捏造，請提醒使用者確認登入帳號、使用條件，或聯絡店家人員協助。"""


def _format_member_context(member: dict, coupons: list | None = None) -> str:
    vip_text = "VIP 會員" if member.get("vip") else "一般會員"
    level = member.get("member_level") or "normal"
    lines = [
        "目前使用者的會員資料（已由系統查證，非使用者自行宣稱）：",
        f"- 姓名：{member.get('name') or '會員'}",
        f"- 會員等級：{level}（{vip_text}）",
        f"- 累積到店次數：{member.get('visit_count', 0)}",
        f"- 累積消費金額：{member.get('total_amount', 0)}",
    ]

    coupons = coupons or []
    lines.append(f"- 優惠券總數：{len(coupons)} 張")
    if coupons:
        lines.append("- 優惠券明細：")
        max_listed = 10
        for coupon in coupons[:max_listed]:
            name = coupon.get("coupon_name") or "優惠券"
            discount = coupon.get("discount_text")
            end_at = coupon.get("end_at_text") or "無期限資料"
            status = coupon.get("status_label") or ""
            detail = f"  - {name}"
            if discount:
                detail += f"，{discount}"
            detail += f"，期限至 {end_at}，狀態：{status}"
            lines.append(detail)
        remaining = len(coupons) - max_listed
        if remaining > 0:
            lines.append(f"  - （其餘 {remaining} 張未列出，請提醒使用者到會員專區查看完整清單）")

    return "\n".join(lines)


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


def ask_llm(
    user_message: str,
    member: dict | None = None,
    coupons: list | None = None,
) -> str:
    """
    回覆單次會員系統客服問題，不保存對話紀錄。

    member：呼叫端（routes/line.py）用 line_user_id 查到的真實會員資料
    （查無此人時傳 None）。
    coupons：該會員的優惠券清單，格式比照 routes/home.py 的
    prepare_member_coupon_rows() 輸出（含 coupon_name、discount_text、
    end_at_text、status_label）。
    兩者會被組成一則額外的 system 訊息一併送給 LLM，讓它能回答
    「我的會員等級」「我有哪些優惠券」之類需要真實資料的問題，
    而不是每次都因為沒有資料而回答查不到。
    """
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

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if member:
        messages.append({
            "role": "system",
            "content": _format_member_context(member, coupons),
        })
    messages.append({"role": "user", "content": user_message.strip()})

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
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


def generate_preference_recommendation(name, preferences):
    """依會員註冊喜好產生到店推薦；失敗時回傳 None 供固定文案備援。"""
    cleaned_preferences = [
        str(preference).strip()
        for preference in (preferences or [])
        if str(preference).strip()
    ]
    if not cleaned_preferences:
        return None

    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return None

    base_url = (
        os.getenv("LLM_BASE_URL", "").strip()
        or _DEFAULT_BASE_URL
    ).rstrip("/")
    model = os.getenv("LLM_MODEL", "").strip() or _DEFAULT_MODEL
    member_name = str(name or "會員").strip() or "會員"
    preference_text = "、".join(cleaned_preferences[:5])
    prompt = (
        "請根據會員註冊時選擇的喜好，產生一則到店 LINE 推薦。"
        f"會員稱呼：{member_name}；喜好：{preference_text}。"
        "請使用繁體中文，語氣親切自然，限 2 句、80 字內。"
        "可以推薦前往相關商品區，但不可捏造折扣、價格、庫存、"
        "優惠券或會員權益，也不要提到你是 AI。"
    )

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
                    {
                        "role": "system",
                        "content": "你是門市的個人化到店推薦助理。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_completion_tokens": 120,
                "enable_thinking": False,
                "stream": False,
            },
            timeout=_REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
        answer = _extract_answer(response.json())
    except (requests.RequestException, ValueError):
        return None

    return answer
