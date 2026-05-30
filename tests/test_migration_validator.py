import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from validators.migration_validator import MigrationValidator

class TestMigrationValidator(unittest.TestCase):
    def setUp(self):
        self.mock_oracle = MagicMock()
        self.mock_pg = MagicMock()
        self.validator = MigrationValidator(self.mock_oracle, self.mock_pg)
        
    def test_validate_row_counts_success(self):
        o_conn = self.mock_oracle.get_connection.return_value.__enter__.return_value
        o_cursor = o_conn.cursor.return_value.__enter__.return_value
        o_cursor.fetchone.return_value = [1500]
        
        p_conn = self.mock_pg.get_connection.return_value.__enter__.return_value
        p_cursor = p_conn.cursor.return_value.__enter__.return_value
        p_cursor.fetchone.return_value = [1500]
        
        is_valid = self.validator.validate_row_counts("USERS")
        self.assertTrue(is_valid)
        
    def test_validate_row_counts_failure(self):
        o_conn = self.mock_oracle.get_connection.return_value.__enter__.return_value
        o_cursor = o_conn.cursor.return_value.__enter__.return_value
        o_cursor.fetchone.return_value = [1500]
        
        p_conn = self.mock_pg.get_connection.return_value.__enter__.return_value
        p_cursor = p_conn.cursor.return_value.__enter__.return_value
        p_cursor.fetchone.return_value = [1499]
        
        is_valid = self.validator.validate_row_counts("USERS")
        self.assertFalse(is_valid)
        
    def test_validate_null_mismatches_success(self):
        o_conn = self.mock_oracle.get_connection.return_value.__enter__.return_value
        o_cursor = o_conn.cursor.return_value.__enter__.return_value
        o_cursor.fetchone.return_value = [5]
        
        p_conn = self.mock_pg.get_connection.return_value.__enter__.return_value
        p_cursor = p_conn.cursor.return_value.__enter__.return_value
        p_cursor.fetchone.return_value = [5]
        
        is_valid = self.validator.validate_null_mismatches("USERS", ["EMAIL"])
        self.assertTrue(is_valid)

    def test_validate_checksums_success(self):
        o_conn = self.mock_oracle.get_connection.return_value.__enter__.return_value
        o_cursor = o_conn.cursor.return_value.__enter__.return_value
        o_cursor.fetchmany.side_effect = [[(1, "Alice")], []]
        
        p_conn = self.mock_pg.get_connection.return_value.__enter__.return_value
        p_cursor = p_conn.cursor.return_value.__enter__.return_value
        p_cursor.fetchmany.side_effect = [[(1, "Alice")], []]
        
        is_valid = self.validator.validate_checksums("USERS", "ID", ["ID", "NAME"])
        self.assertTrue(is_valid)

    def test_validate_checksums_failure(self):
        o_conn = self.mock_oracle.get_connection.return_value.__enter__.return_value
        o_cursor = o_conn.cursor.return_value.__enter__.return_value
        o_cursor.fetchmany.side_effect = [[(1, "Alice")], []]
        
        p_conn = self.mock_pg.get_connection.return_value.__enter__.return_value
        p_cursor = p_conn.cursor.return_value.__enter__.return_value
        p_cursor.fetchmany.side_effect = [[(1, "Bob")], []] # Different data
        
        is_valid = self.validator.validate_checksums("USERS", "ID", ["ID", "NAME"])
        self.assertFalse(is_valid)

if __name__ == "__main__":
    unittest.main()
