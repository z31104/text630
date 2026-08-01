import os
import unittest
from unittest.mock import Mock, patch

from database import db


class DatabaseConnectionPoolTests(unittest.TestCase):
    def test_pool_is_created_once_and_reused(self):
        original_pool = db._connection_pool
        fake_pool = Mock()
        first_connection = Mock()
        second_connection = Mock()
        fake_pool.get_connection.side_effect = [
            first_connection,
            second_connection,
        ]

        try:
            db._connection_pool = None
            with (
                patch.dict(
                    os.environ,
                    {
                        "DB_POOL_ENABLED": "true",
                        "DB_POOL_SIZE": "3",
                        "DB_HOST": "db.example",
                        "DB_PORT": "3306",
                        "DB_USER": "user",
                        "DB_PASSWORD": "password",
                        "DB_NAME": "database",
                    },
                    clear=False,
                ),
                patch.object(
                    db.pooling,
                    "MySQLConnectionPool",
                    return_value=fake_pool,
                ) as pool_factory,
            ):
                self.assertIs(first_connection, db.get_connection())
                self.assertIs(second_connection, db.get_connection())

            pool_factory.assert_called_once()
            self.assertEqual(2, fake_pool.get_connection.call_count)
        finally:
            db._connection_pool = original_pool


if __name__ == "__main__":
    unittest.main()
