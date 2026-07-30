"""
AI 組 API 使用的資料查詢服務。
"""

from database.db import get_connection, get_member_level_text


def get_current_visitors(timeout_seconds=60):
    """
    查詢目前仍在店內的會員與固定散客。

    同一個人在多台攝影機有有效紀錄時，只回傳最後看到的一筆。
    """

    conn = None
    cursor = None

    try:
        timeout_seconds = int(timeout_seconds)

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必須大於 0")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            rl.log_id,
            rl.subject_type,
            rl.member_id,
            rl.visitor_id,
            rl.visitor_code,
            rl.camera_id,
            rl.camera_location,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.name, rl.name)
                ELSE rl.name
            END AS name,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.vip, rl.vip)
                ELSE rl.vip
            END AS vip,
            rl.confidence,
            CASE
                WHEN rl.subject_type = 'member'
                    THEN COALESCE(m.member_level, rl.member_level)
                ELSE rl.member_level
            END AS member_level,
            rl.recognition_status,
            rl.visit_status,
            rl.visit_time,
            rl.recognized_at,
            rl.last_seen_at,
            rl.leave_time,
            GREATEST(
                TIMESTAMPDIFF(SECOND, rl.visit_time, NOW()),
                0
            ) AS stay_seconds,
            ROUND(
                GREATEST(
                    TIMESTAMPDIFF(SECOND, rl.visit_time, NOW()),
                    0
                ) / 60.0,
                2
            ) AS stay_minutes
        FROM recognition_logs AS rl
        LEFT JOIN members AS m
          ON m.member_id = rl.member_id
         AND rl.subject_type = 'member'
        WHERE rl.subject_type IN ('member', 'visitor')
          AND rl.recognition_status = 'recognized'
          AND rl.visit_status IN ('arrived', 'staying')
          AND rl.leave_time IS NULL
          AND COALESCE(rl.last_seen_at, rl.visit_time, rl.recognized_at)
              >= DATE_SUB(NOW(), INTERVAL %s SECOND)
        ORDER BY COALESCE(
                     rl.last_seen_at,
                     rl.visit_time,
                     rl.recognized_at
                 ) DESC,
                 rl.log_id DESC
        """

        cursor.execute(sql, (timeout_seconds,))
        rows = cursor.fetchall()

        current_visitors = []
        seen_subjects = set()

        for row in rows:
            if row.get("subject_type") == "member":
                subject_id = row.get("member_id")
            else:
                subject_id = row.get("visitor_id")

            subject_key = (row.get("subject_type"), subject_id)

            if subject_id is None or subject_key in seen_subjects:
                continue

            seen_subjects.add(subject_key)
            row["member_level_text"] = get_member_level_text(
                row.get("member_level")
            )
            current_visitors.append(row)

        return current_visitors

    except (TypeError, ValueError):
        print("取得目前店內人員失敗：timeout_seconds 必須是正整數")
        raise

    except Exception as e:
        print("取得目前店內人員失敗：", e)
        raise

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()
