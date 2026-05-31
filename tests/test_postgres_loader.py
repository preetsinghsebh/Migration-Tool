import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from connectors.postgres import PostgresConnector
from loaders.postgres_loader import PostgresLoader

class TestPostgresLoader(unittest.TestCase):
    def setUp(self):
        # Mock the PostgresConnector, Connection, and Cursor
        self.mock_connector = MagicMock(spec=PostgresConnector)
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        
        # Setup context managers for `with connector.get_connection() as conn` 
        # and `with conn.cursor() as cursor`
        self.mock_connector.get_connection.return_value.__enter__.return_value = self.mock_conn
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        
        self.loader = PostgresLoader(self.mock_connector)
        
    @patch('loaders.postgres_loader.execute_values')
    def test_load_table_success(self, mock_execute_values):
        # Create a mock generator that yields 2 batches of data
        def data_generator():
            yield [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ]
            yield [
                {"id": 3, "name": "Charlie"}
            ]
            
        total_inserted = self.loader.load_table("users", data_generator())
        
        self.assertEqual(total_inserted, 3)
        self.assertEqual(mock_execute_values.call_count, 2)
        
        # Verify the first call to execute_values
        call_args_1 = mock_execute_values.call_args_list[0][0]
        self.assertEqual(call_args_1[0], self.mock_cursor)
        self.assertIn('INSERT INTO "users" ("id", "name") VALUES %s', call_args_1[1])
        self.assertEqual(call_args_1[2], [[1, "Alice"], [2, "Bob"]])
        
        # Verify commit was called to finalize the transaction
        self.mock_conn.commit.assert_called_once()
        self.mock_conn.rollback.assert_not_called()

    @patch('loaders.postgres_loader.execute_values')
    def test_load_table_rollback_on_error(self, mock_execute_values):
        # Simulate a database failure during insertion
        mock_execute_values.side_effect = Exception("Database error")
        
        def data_generator():
            yield [{"id": 1}]
            
        with self.assertRaises(Exception) as context:
            self.loader.load_table("users", data_generator())
            
        self.assertIn("Database error", str(context.exception))
        
        # Verify rollback was called instead of commit
        self.mock_conn.rollback.assert_called_once()
        self.mock_conn.commit.assert_not_called()

if __name__ == "__main__":
    unittest.main()
