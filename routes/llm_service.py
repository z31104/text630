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
如果對話中有提供「目前使用者的會員資料」，代表這是系統查證過的真實資料；
只有在使用者的問題確實需要查會員等級、優惠券、消費金額、VIP 升級進度、
抽獎結果或註冊喜好類別時，才根據這份資料回答，
不要說自己查不到或無法查詢會員系統。
只回答使用者這次問題實際問到的項目就好，不要順便補充其他沒被問到的
會員資料細項（例如使用者只問優惠券，就不要在同一則回覆裡順便講
VIP 升級進度、抽獎結果或到店次數），除非使用者的問題本來就一次問了
多個項目。
使用者只是打招呼、閒聊或問跟會員資料無關的問題時，不要主動列出或提及
會員資料的任何內容，回一句自然的寒暄或回答就好。
如果沒有提供會員資料，或使用者問的是會員系統相關但超出提供資料範圍的內容，
不可自行捏造，請提醒使用者確認登入帳號、使用條件，或聯絡店家人員協助。"""


def _format_amount(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


_LOTTERY_PRIZE_STATUS_LABELS = {
    "unused": "可兌換",
    "redeemed": "已兌換",
    "expired": "已過期",
}


def _format_member_context(
    member: dict,
    coupons: list | None = None,
    vip_upgrade_threshold: int | None = None,
    preferences: list | None = None,
    lottery_prize: dict | None = None,
) -> str:
    vip_text = "VIP 會員" if member.get("vip") else "一般會員"
    level = member.get("member_level") or "normal"
    total_amount = member.get("total_amount") or 0
    lines = [
        "目前使用者的會員資料（已由系統查證，非使用者自行宣稱）：",
        f"- 姓名：{member.get('name') or '會員'}",
        f"- 會員等級：{level}（{vip_text}）",
        f"- 累積到店次數：{member.get('visit_count', 0)}",
        f"- 累積消費金額：{_format_amount(total_amount)} 元",
    ]

    if preferences:
        lines.append(f"- 註冊時勾選的喜好類別：{'、'.join(preferences)}")

    if vip_upgrade_threshold is not None:
        if member.get("vip"):
            lines.append("- VIP 升級門檻：已達成，目前已是 VIP 會員")
        else:
            remaining = max(
                float(vip_upgrade_threshold) - float(total_amount),
                0,
            )
            lines.append(
                f"- VIP 升級門檻：累積消費滿 {_format_amount(vip_upgrade_threshold)} 元"
                f"自動升級為 VIP，目前還差 {_format_amount(remaining)} 元"
            )

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

    if lottery_prize:
        status_text = _LOTTERY_PRIZE_STATUS_LABELS.get(
            lottery_prize.get("status"),
            lottery_prize.get("status") or "",
        )
        expires_text = lottery_prize.get("expires_at_text") or "無期限資料"
        lines.append(
            f"- 抽獎結果：已抽中「{lottery_prize.get('prize_name')}」，"
            f"狀態：{status_text}，兌換期限至 {expires_text}"
        )
    else:
        lines.append("- 抽獎結果：尚未抽中最終獎項（可能還沒抽獎，或抽獎流程尚未完成）")

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
    vip_upgrade_threshold: int | None = None,
    preferences: list | None = None,
    lottery_prize: dict | None = None,
) -> str:
    """
    回覆單次會員系統客服問題，不保存對話紀錄。

    member：呼叫端（routes/line.py）用 line_user_id 查到的真實會員資料
    （查無此人時傳 None）。
    coupons：該會員的優惠券清單，格式比照 routes/home.py 的
    prepare_member_coupon_rows() 輸出（含 coupon_name、discount_text、
    end_at_text、status_label）。
    vip_upgrade_threshold：升級 VIP 所需的累積消費金額門檻
    （呼叫端傳 routes/line.py 的 VIP_UPGRADE_THRESHOLD），
    用來讓 LLM 回答「還差多少錢升級 VIP」。
    preferences：該會員註冊時勾選的喜好類別清單（database.db 的
    get_member_preferences() 輸出，例如 ["餐廳"]）。
    lottery_prize：該會員這次抽獎活動抽中的最終獎項（database.db 的
    get_member_prize() 輸出經呼叫端整理成 {"prize_name", "status",
    "expires_at_text"}；查無資料或尚未抽獎時傳 None）。
    以上都會被組成一則額外的 system 訊息一併送給 LLM，讓它能回答
    「我的會員等級」「我有哪些優惠券」「我要怎麼升級」「我的喜好」
    「我抽獎抽中什麼」之類需要真實資料的問題，而不是每次都因為
    沒有資料而回答查不到。
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
            "content": _format_member_context(
                member,
                coupons,
                vip_upgrade_threshold,
                preferences,
                lottery_prize,
            ),
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
