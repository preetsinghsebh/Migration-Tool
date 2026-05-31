import sys
import os
import logging
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import setup_logging, ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
from connectors.oracle import OracleConnector
from extractors.schema_extractor import SchemaExtractor

class TestSchemaExtractor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_logging()
        cls.logger = logging.getLogger(__name__)
        cls.logger.info("--- Starting Schema Extractor Module Test (Mocked) ---")

    @patch('connectors.oracle.oracledb.create_pool')
    def test_schema_extraction_and_export(self, mock_oracledb_pool):
        # 1. Setup Mocks
        mock_oracle_conn = MagicMock()
        mock_oracle_cursor = MagicMock()

        # Mocking the cursor to handle get_tables_generator and get_table_columns
        # get_tables query contains 'user_tables'
        # get_table_columns query contains 'user_tab_columns'
        
        def execute_side_effect(query, params=None):
            if "user_tables" in query:
                # Mocking tables
                mock_oracle_cursor.fetchmany.side_effect = [
                    [("EMPLOYEES",), ("DEPARTMENTS",)],
                    []
                ]
            elif "user_tab_columns" in query:
                # Mocking columns based on params
                if params and params[0] == "EMPLOYEES":
                    mock_oracle_cursor.__iter__.return_value = iter([
                        ("EMP_ID", "NUMBER", 10, 0, "N"),
                        ("EMP_NAME", "VARCHAR2", 50, None, "Y")
                    ])
                elif params and params[0] == "DEPARTMENTS":
                    mock_oracle_cursor.__iter__.return_value = iter([
                        ("DEPT_ID", "NUMBER", 4, 0, "N"),
                        ("DEPT_NAME", "VARCHAR2", 50, None, "N")
                    ])
            elif "user_constraints" in query:
                if params and params[0] == "EMPLOYEES":
                    mock_oracle_cursor.__iter__.return_value = iter([
                        ("PK_EMP", "P", "EMP_ID", None)
                    ])
                elif params and params[0] == "DEPARTMENTS":
                    mock_oracle_cursor.__iter__.return_value = iter([
                        ("PK_DEPT", "P", "DEPT_ID", None)
                    ])
        
        mock_oracle_cursor.execute.side_effect = execute_side_effect
        mock_oracle_conn.cursor.return_value.__enter__.return_value = mock_oracle_cursor
        
        mock_oracle_pool_instance = MagicMock()
        mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
        mock_oracledb_pool.return_value = mock_oracle_pool_instance

        # 2. Initialize Connector and Extractor
        connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
        connector.initialize_pool(min_conn=1, max_conn=1)
        extractor = SchemaExtractor(connector)
        
        # 3. Test Export with a temporary file
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            exported_count = extractor.export_schema_to_json(tmp_path)
            self.assertEqual(exported_count, 2)
            
            # 4. Verify JSON content
            with open(tmp_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                
            self.assertIsInstance(content, list)
            self.assertEqual(len(content), 2)
            
            # Check structure
            self.assertEqual(content[0]["table_name"], "EMPLOYEES")
            self.assertEqual(len(content[0]["columns"]), 2)
            self.assertEqual(content[0]["columns"][0]["name"], "EMP_ID")
            self.assertEqual(content[0]["columns"][0]["datatype"], "NUMBER")
            self.assertEqual(content[0]["columns"][0]["precision"], 10)
            self.assertEqual(content[0]["columns"][0]["scale"], 0)
            self.assertEqual(content[0]["columns"][0]["nullable"], False)
            
            # Check constraints
            self.assertIn("constraints", content[0])
            self.assertEqual(len(content[0]["constraints"]), 1)
            self.assertEqual(content[0]["constraints"][0]["name"], "PK_EMP")
            self.assertEqual(content[0]["constraints"][0]["type"], "P")
            self.assertEqual(content[0]["constraints"][0]["columns"], ["EMP_ID"])
            
            self.assertEqual(content[1]["table_name"], "DEPARTMENTS")
            
            self.logger.info("JSON file structure matches expected format successfully.")

        finally:
            connector.close_pool()
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch('connectors.oracle.oracledb.create_pool')
    def test_sequence_extraction(self, mock_oracledb_pool):
        mock_oracle_conn = MagicMock()
        mock_oracle_cursor = MagicMock()

        # Mock sequence query results
        mock_oracle_cursor.__iter__.return_value = iter([
            ("SEQ_USERS", 1, 999999, 1, "N", 20, 42)
        ])
        mock_oracle_conn.cursor.return_value.__enter__.return_value = mock_oracle_cursor
        
        mock_oracle_pool_instance = MagicMock()
        mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
        mock_oracledb_pool.return_value = mock_oracle_pool_instance

        connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
        connector.initialize_pool(min_conn=1, max_conn=1)
        extractor = SchemaExtractor(connector)

        try:
            sequences = extractor.get_sequences()
            self.assertEqual(len(sequences), 1)
            self.assertEqual(sequences[0]["name"], "SEQ_USERS")
            self.assertEqual(sequences[0]["min_value"], 1)
            self.assertEqual(sequences[0]["max_value"], 999999)
            self.assertEqual(sequences[0]["increment_by"], 1)
            self.assertEqual(sequences[0]["cycle"], False)
            self.assertEqual(sequences[0]["cache_size"], 20)
            self.assertEqual(sequences[0]["last_number"], 42)
        finally:
            connector.close_pool()

if __name__ == "__main__":
    unittest.main()
