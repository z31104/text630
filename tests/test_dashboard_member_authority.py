import unittest
from unittest.mock import patch

from database import db


class FakeCursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def cursor(self, dictionary=False):
        return self.cursor_instance

    def is_connected(self):
        return True

    def close(self):
        pass


class DashboardMemberAuthorityTests(unittest.TestCase):
    def test_today_vip_uses_current_member_master_data(self):
        cursor = FakeCursor(row={
            "today_visit_count": 1,
            "today_visitors": 1,
            "today_vip": 1,
            "today_visitors_fixed": 0,
            "current_people": 0,
            "today_new_members": 1,
            "average_stay_minutes": 3.9,
        })
        connection = FakeConnection(cursor)

        with patch.object(
            db,
            "get_connection",
            return_value=connection,
        ):
            summary = db.get_dashboard_summary()

        sql = cursor.executed[0][0]
        self.assertIn("JOIN members AS m", sql)
        self.assertIn("m.vip = TRUE", sql)
        self.assertIn("m.member_level = 'vip'", sql)
        self.assertEqual(1, summary["today_vip"])

    def test_recognition_rows_use_current_member_level(self):
        cursor = FakeCursor(rows=[{
            "log_id": 60,
            "subject_type": "member",
            "member_id": 12,
            "vip": 1,
            "member_level": "vip",
        }])
        connection = FakeConnection(cursor)

        with patch.object(
            db,
            "get_connection",
            return_value=connection,
        ):
            rows = db.get_recognition_logs(limit=10)

        sql = cursor.executed[0][0]
        self.assertIn("LEFT JOIN members AS m", sql)
        self.assertIn("COALESCE(m.vip, rl.vip)", sql)
        self.assertIn(
            "COALESCE(m.member_level, rl.member_level)",
            sql,
        )
        self.assertEqual("VIP 會員", rows[0]["member_level_text"])


if __name__ == "__main__":
    unittest.main()
