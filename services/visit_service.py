def build_subject_key(
    subject_type: str,
    member_id: int | None = None,
    visitor_id: int | None = None,
) -> str | None:
    """
    根據辨識主體類型，產生 active visit 使用的唯一 key。

    會員：
        member:4

    固定散客：
        visitor:7

    unknown、none 或缺少有效 ID：
        回傳 None
    """

    if subject_type == "member" and member_id is not None:
        return f"member:{member_id}"

    if subject_type == "visitor" and visitor_id is not None:
        return f"visitor:{visitor_id}"

    return None