"""
LLM 呼叫模組的暫時雛形（stub）。

Roger 之後會提供正式的 ask_llm()，介面完全比照這裡：
ask_llm(user_message: str) -> str

正式版做好後，直接替換這個檔案的實作即可，
呼叫端（routes/line.py）不需要跟著修改。
"""


def ask_llm(user_message: str) -> str:
    text = (user_message or "").strip()

    if not text:
        return "請輸入訊息內容"

    return f"（LLM 雛形回覆）你說的是：{text}"
