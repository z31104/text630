import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# 讓這支單元測試在沒有安裝 mysql-connector-python 的純 Python
# 環境也能載入 database.db；測試本身不會連線真實資料庫。
if "mysql.connector" not in sys.modules:
    mysql_module = types.ModuleType("mysql")
    connector_module = types.ModuleType("mysql.connector")

    class DummyPool:
        def __init__(self, *args, **kwargs):
            pass

        def get_connection(self):
            raise RuntimeError("單元測試不應連線真實資料庫")

    connector_module.connect = lambda **kwargs: (_ for _ in ()).throw(
        RuntimeError("單元測試不應連線真實資料庫")
    )
    connector_module.pooling = types.SimpleNamespace(
        MySQLConnectionPool=DummyPool
    )
    mysql_module.connector = connector_module
    sys.modules["mysql"] = mysql_module
    sys.modules["mysql.connector"] = connector_module

if "dotenv" not in sys.modules:
    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_module

from database import db


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.closed = False
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, row):
        self.cursor_instance = FakeCursor(row)
        self.closed = False

    def cursor(self, dictionary=False):
        return self.cursor_instance

    def is_connected(self):
        return not self.closed

    def close(self):
        self.closed = True


class DatabaseBenefitTests(unittest.TestCase):
    def test_month_bounds_handles_leap_year(self):
        start_at, end_at = db._month_bounds("2028-02-10")

        self.assertEqual(
            start_at.isoformat(sep=" "),
            "2028-02-01 00:00:00",
        )
        self.assertEqual(
            end_at.isoformat(sep=" "),
            "2028-02-29 23:59:59",
        )

    def test_get_member_benefit_returns_vip_5_percent(self):
        fake_connection = FakeConnection({
            "member_id": 1,
            "name": "王小明",
            "vip": True,
            "member_level": "vip",
        })

        with patch.object(
            db,
            "get_connection",
            return_value=fake_connection,
        ):
            result = db.get_member_benefit(1)

        self.assertTrue(result["eligible"])
        self.assertEqual(
            result["benefit_code"],
            "VIP_DISCOUNT_5",
        )
        self.assertEqual(result["discount_value"], 5.0)

    def test_calculate_member_discount_vip(self):
        benefit = {
            "member_id": 1,
            "name": "王小明",
            "vip": True,
            "member_level": "vip",
            "eligible": True,
            "benefit_code": "VIP_DISCOUNT_5",
            "benefit_name": "VIP 會員 5% 禮遇",
            "discount_type": "percentage",
            "discount_value": 5.0,
        }

        with patch.object(
            db,
            "get_member_benefit",
            return_value=benefit,
        ):
            result = db.calculate_member_discount(
                1,
                1000,
            )

        self.assertEqual(result["discount_amount"], 50.0)
        self.assertEqual(result["final_amount"], 950.0)

    def test_calculate_member_discount_normal_member(self):
        benefit = {
            "member_id": 2,
            "name": "李小華",
            "vip": False,
            "member_level": "normal",
            "eligible": False,
            "benefit_code": None,
            "benefit_name": None,
            "discount_type": None,
            "discount_value": 0.0,
        }

        with patch.object(
            db,
            "get_member_benefit",
            return_value=benefit,
        ):
            result = db.calculate_member_discount(
                2,
                "1000.00",
            )

        self.assertEqual(result["discount_amount"], 0.0)
        self.assertEqual(result["final_amount"], 1000.0)


class Week4SchemaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema_text = (
            Path(__file__).resolve().parents[1]
            / "database"
            / "schema.sql"
        ).read_text(encoding="utf-8")

    def _table_body(self, table_name):
        match = re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{table_name}\s*"
            rf"\((.*?)\)\s*;",
            self.schema_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            f"schema.sql 缺少資料表：{table_name}",
        )
        return match.group(1)

    def assert_table_has_columns(
        self,
        table_name,
        required_columns,
    ):
        body = self._table_body(table_name)

        for column in required_columns:
            self.assertRegex(
                body,
                rf"(?m)^\s*{column}\s+",
                f"{table_name} 缺少欄位：{column}",
            )

    def test_week4_cloud_fields_exist(self):
        contracts = {
            "members": [
                "member_id",
                "name",
                "phone",
                "vip",
                "member_level",
                "line_user_id",
                "total_amount",
                "favorite_product",
                "face_image",
                "registration_source",
                "created_at",
                "updated_at",
                "last_visit_time",
                "total_visit_time",
                "total_visit_count",
                "updated_by",
            ],
            "face_images": [
                "face_id",
                "member_id",
                "image_path",
                "encoding_data",
                "created_at",
            ],
            "recognition_logs": [
                "log_id",
                "subject_type",
                "member_id",
                "visitor_id",
                "visitor_code",
                "camera_id",
                "camera_location",
                "name",
                "vip",
                "line_user_id",
                "confidence",
                "member_level",
                "recognition_status",
                "visit_status",
                "recognized_at",
                "visit_time",
                "last_seen_at",
                "leave_time",
                "stay_seconds",
                "notification_sent",
                "coupon_sent",
                "lottery_status",
                "created_at",
            ],
            "visitors": [
                "visitor_id",
                "visitor_code",
                "display_name",
                "first_seen_at",
                "last_seen_at",
                "visitor_visit_count",
                "converted_member_id",
                "best_face_image",
                "created_at",
                "updated_at",
            ],
            "vip_notifications": [
                "notification_id",
                "member_id",
                "log_id",
                "line_user_id",
                "message",
                "status",
                "sent_at",
                "notification_type",
                "retry_count",
                "response_message",
                "created_at",
            ],
            "member_coupons": [
                "member_coupon_id",
                "member_id",
                "coupon_id",
                "receive_time",
                "used_time",
                "status",
            ],
            "lottery_records": [
                "lottery_id",
                "member_id",
                "lottery_name",
                "prize",
                "draw_time",
                "status",
            ],
            "camera_locations": [
                "camera_id",
                "camera_name",
                "camera_location",
                "status",
            ],
        }

        for table_name, required_columns in contracts.items():
            with self.subTest(table=table_name):
                self.assert_table_has_columns(
                    table_name,
                    required_columns,
                )

    def test_removed_duplicate_fields_are_not_schema_columns(self):
        members_body = self._table_body("members")
        recognition_body = self._table_body(
            "recognition_logs"
        )

        self.assertNotRegex(
            members_body,
            r"(?m)^\s*visit_count\s+",
        )
        self.assertNotRegex(
            recognition_body,
            r"(?m)^\s*stay_minutes\s+",
        )


if __name__ == "__main__":
    unittest.main()