from datetime import datetime
from typing import Any, Callable


def build_subject_key(
    subject_type: str,
    member_id: int | None = None,
    visitor_id: int | None = None,
) -> str | None:
    """
    根據辨識主體類型，產生 active visit 使用的唯一 key。
    """

    if subject_type == "member" and member_id is not None:
        return f"member:{member_id}"

    if subject_type == "visitor" and visitor_id is not None:
        return f"visitor:{visitor_id}"

    return None


def datetime_to_timestamp(value: Any) -> float | None:
    """將資料庫 datetime 或時間字串轉成 Unix timestamp。"""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.timestamp()

    if isinstance(value, str):
        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d %H:%M:%S"
            ).timestamp()
        except ValueError:
            return None

    return None


def datetime_to_text(value: Any) -> str | None:
    """將資料庫 datetime 或時間字串統一轉成文字。"""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, str):
        return value

    return None


def handle_recognition(
    *,
    result: dict,
    current_time: float,
    current_time_text: str,
    active_visits: dict,
    active_visits_lock,
    camera_id: str,
    leave_timeout: int,
    last_seen_update_interval: int,
    get_active_visit_fn: Callable,
    create_log_fn: Callable,
    update_last_seen_fn: Callable,
    close_visit_fn: Callable,
    notify_fn: Callable,
) -> dict:
    """
    統一處理正式會員與固定散客的 Active Visit：

    1. 記憶體無紀錄時先查 DB active visit
    2. 未過期則恢復原 log_id
    3. 過期則關閉舊 visit，再建立新 visit
    4. 持續辨識時定期更新 last_seen_at
    """

    member_id = result.get("member_id")
    subject_type = result.get("subject_type")
    visitor_id = result.get("visitor_id")

    subject_key = build_subject_key(
        subject_type=subject_type,
        member_id=member_id,
        visitor_id=visitor_id,
    )

    if subject_key is None:
        return {"action": "ignored", "log_id": None}

    subject_id = (
        member_id if subject_type == "member"
        else visitor_id
    )

    with active_visits_lock:
        if subject_key not in active_visits:
            db_active_visit = get_active_visit_fn(
                subject_type=subject_type,
                subject_id=subject_id,
                camera_id=camera_id,
            )

            if db_active_visit is not None:
                db_log_id = db_active_visit.get("log_id")
                db_visit_time = db_active_visit.get("visit_time")
                db_last_seen_at = (
                    db_active_visit.get("last_seen_at")
                    or db_visit_time
                    or db_active_visit.get("recognized_at")
                )

                visit_timestamp = (
                    datetime_to_timestamp(db_visit_time)
                    or current_time
                )
                last_seen_timestamp = (
                    datetime_to_timestamp(db_last_seen_at)
                    or visit_timestamp
                )

                elapsed_seconds = max(
                    current_time - last_seen_timestamp,
                    0,
                )

                if elapsed_seconds < leave_timeout:
                    restored_visit_time = (
                        datetime_to_text(db_visit_time)
                        or current_time_text
                    )

                    restored_recognized_at = datetime_to_text(
                        db_active_visit.get("recognized_at")
                    )

                    # 將資料庫恢復到的 Active Visit 狀態，
                    # 同步回本次 AI 辨識結果。
                    result["log_id"] = db_log_id
                    result["visit_status"] = "staying"
                    result["recognized_at"] = (
                        restored_recognized_at
                        or restored_visit_time
                    )
                    result["visit_time"] = restored_visit_time
                    result["last_seen_at"] = current_time_text
                    result["leave_time"] = None
                    result["stay_seconds"] = db_active_visit.get(
                        "stay_seconds",
                        0
                    )

                    # visitor 在其他 Flask process 轉成 member 後，
                    # DB log 仍保留原 visitor_id 供追溯。恢復 member
                    # visit 時清掉本機舊 visitor key，避免兩套 active state。
                    converted_visitor_id = db_active_visit.get(
                        "visitor_id"
                    )
                    if (
                        subject_type == "member"
                        and converted_visitor_id is not None
                    ):
                        old_visitor_key = build_subject_key(
                            subject_type="visitor",
                            visitor_id=converted_visitor_id,
                        )
                        active_visits.pop(old_visitor_key, None)

                    active_visits[subject_key] = {
                        "log_id": db_log_id,
                        "result": result,
                        "visit_timestamp": visit_timestamp,
                        "visit_time": restored_visit_time,
                        "last_seen_timestamp": current_time,
                        "last_seen_at": current_time_text,
                        "last_db_update_timestamp": current_time,
                    }

                    update_last_seen_fn(
                        log_id=db_log_id,
                        last_seen_at=current_time_text,
                    )

                    notification_status = None
                    if (
                        subject_type == "member"
                        and db_active_visit.get(
                            "notification_sent"
                        ) is not True
                    ):
                        notification_result = dict(result)
                        notification_result["visit_status"] = "arrived"
                        notification_result["notification_sent"] = False
                        notification_status = notify_fn(
                            notification_result,
                            log_id=db_log_id,
                        )
                        if notification_status == "sent":
                            result["notification_sent"] = True
                            active_visits[subject_key][
                                "result"
                            ]["notification_sent"] = True

                    return {
                        "action": "restored",
                        "log_id": db_log_id,
                        "member_id": member_id,
                        "visitor_id": visitor_id,
                        "subject_type": subject_type,
                        "notification_status": notification_status,
                    }

                leave_timestamp = min(
                    last_seen_timestamp + leave_timeout,
                    current_time,
                )
                leave_time = datetime.fromtimestamp(
                    leave_timestamp
                ).strftime("%Y-%m-%d %H:%M:%S")

                stay_seconds = max(
                    int(round(leave_timestamp - visit_timestamp)),
                    0,
                )
                stay_minutes = round(stay_seconds / 60, 2)

                close_visit_fn(
                    log_id=db_log_id,
                    last_seen_at=(
                        datetime_to_text(db_last_seen_at)
                        or leave_time
                    ),
                    leave_time=leave_time,
                    stay_seconds=stay_seconds,
                    stay_minutes=stay_minutes,
                )

            log_id = create_log_fn(
                result,
                visit_time=current_time_text,
                leave_time=None,
                stay_minutes=0,
                visit_status="arrived",
                camera_id=camera_id,
            )

            if log_id is None:
                return {
                    "action": "failed",
                    "log_id": None,
                    "member_id": member_id,
                    "visitor_id": visitor_id,
                    "subject_type": subject_type,
                }

            # Recognition Log 成功建立後，
            # 將正式到店資料同步回 AI 統一辨識結果。
            result["log_id"] = log_id
            result["visit_status"] = "arrived"
            result["recognized_at"] = current_time_text
            result["visit_time"] = current_time_text
            result["last_seen_at"] = current_time_text
            result["leave_time"] = None
            result["stay_seconds"] = 0

            active_visits[subject_key] = {
                "log_id": log_id,
                "result": result,
                "visit_timestamp": current_time,
                "visit_time": current_time_text,
                "last_seen_timestamp": current_time,
                "last_seen_at": current_time_text,
                "last_db_update_timestamp": current_time,
            }

            notification_status = notify_fn(
                result,
                log_id=log_id,
            )

            return {
                "action": "created",
                "log_id": log_id,
                "member_id": member_id,
                "visitor_id": visitor_id,
                "subject_type": subject_type,
                "visit_status": "arrived",
                "notification_status": notification_status,
            }

        visit_data = active_visits[subject_key]

        # 將目前進行中的 Active Visit 資料，
        # 同步回這一次的 AI 辨識結果。
        result["log_id"] = visit_data.get("log_id")
        result["visit_status"] = "staying"
        result["visit_time"] = visit_data.get("visit_time")
        result["last_seen_at"] = current_time_text
        result["leave_time"] = None

        visit_timestamp = visit_data.get("visit_timestamp")

        if visit_timestamp is not None:
            result["stay_seconds"] = max(
                int(round(current_time - visit_timestamp)),
                0
            )
        else:
            result["stay_seconds"] = 0

        visit_data["result"] = result
        visit_data["last_seen_timestamp"] = current_time
        visit_data["last_seen_at"] = current_time_text

        # VIP 店員推播曾失敗時，同一筆 active visit 不必等到
        # Flask 重啟才重試。資料庫的 log_id 唯一鍵會阻止已成功
        # 或仍在處理中的通知被重複發送。
        if (
            subject_type == "member"
            and result.get("notification_sent") is not True
        ):
            notification_result = dict(result)
            notification_result["visit_status"] = "arrived"
            notification_result["notification_sent"] = False
            notification_status = notify_fn(
                notification_result,
                log_id=visit_data.get("log_id"),
            )
            if notification_status == "sent":
                result["notification_sent"] = True
                visit_data["result"]["notification_sent"] = True

        last_db_update_timestamp = visit_data.get(
            "last_db_update_timestamp",
            0,
        )

        if (
            current_time - last_db_update_timestamp
            >= last_seen_update_interval
        ):
            log_id = visit_data.get("log_id")

            update_last_seen_fn(
                log_id=log_id,
                last_seen_at=current_time_text,
            )

            visit_data["last_db_update_timestamp"] = current_time

            return {
                "action": "updated",
                "log_id": log_id,
                "member_id": member_id,
                "visitor_id": visitor_id,
                "subject_type": subject_type,
                "visit_status": "staying",
            }

        return {
            "action": "seen",
            "log_id": visit_data.get("log_id"),
            "member_id": member_id,
            "visitor_id": visitor_id,
            "subject_type": subject_type,
            "visit_status": "staying",
        }

def close_timeout_visits(
    *,
    current_time: float,
    active_visits: dict,
    active_visits_lock,
    leave_timeout: int,
    close_visit_fn: Callable,
    current_time_text_fn: Callable[[], str],
) -> list[dict]:
    """
    關閉超過 leave_timeout 未再次出現的 active visit。

    回傳已成功關閉的 visit 清單，供 camera.py 顯示紀錄。
    """

    closed_visits: list[dict] = []
    leaving_subject_keys: list[str] = []

    with active_visits_lock:
        for subject_key, visit_data in list(active_visits.items()):
            result = visit_data.get("result", {})
            member_id = result.get("member_id")
            visitor_id = result.get("visitor_id")

            last_seen_timestamp = visit_data.get("last_seen_timestamp")
            if last_seen_timestamp is None:
                continue

            elapsed_seconds = current_time - last_seen_timestamp
            if elapsed_seconds < leave_timeout:
                continue

            log_id = visit_data.get("log_id")
            last_seen_at = (
                visit_data.get("last_seen_at")
                or current_time_text_fn()
            )
            leave_time = current_time_text_fn()

            visit_timestamp = visit_data.get(
                "visit_timestamp",
                current_time,
            )

            stay_seconds = max(
                int(round(current_time - visit_timestamp)),
                0,
            )
            stay_minutes = round(stay_seconds / 60, 2)

            try:
                closed = close_visit_fn(
                    log_id=log_id,
                    last_seen_at=last_seen_at,
                    leave_time=leave_time,
                    stay_seconds=stay_seconds,
                    stay_minutes=stay_minutes,
                )
            except Exception:
                # 真正的資料庫例外保留 active visit，稍後再重試。
                continue

            if closed is None:
                # face_service 使用 None 表示資料庫例外。
                # 保留 active visit，避免一次連線錯誤造成狀態遺失。
                continue

            leaving_subject_keys.append(subject_key)

            # True 表示本次成功關閉；False 表示 DB 已不是 active
            # （例如其他流程已先關閉），兩者都應移除記憶體 key。
            if not closed:
                continue

            closed_visits.append(
                {
                    "subject_key": subject_key,
                    "member_id": member_id,
                    "visitor_id": visitor_id,
                    "log_id": log_id,
                    "leave_time": leave_time,
                    "stay_seconds": stay_seconds,
                    "stay_minutes": stay_minutes,
                }
            )

        for subject_key in leaving_subject_keys:
            active_visits.pop(subject_key, None)

    return closed_visits

