import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main

class TestMainOrchestrator(unittest.TestCase):
    
    @patch('main.PostgresConnector')
    @patch('main.OracleConnector')
    @patch('main.SchemaExtractor')
    @patch('main.DDLGenerator')
    @patch('main.OracleExtractor')
    @patch('main.PostgresLoader')
    @patch('main.MigrationValidator')
    @patch('main.execute_postgres_scripts')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='[{"table_name": "TEST_TABLE", "columns": [{"name": "ID", "type": "NUMBER"}], "constraints": [{"type": "P", "column_name": "ID"}]}]')
    @patch('os.makedirs')
    def test_main_execution_flow(self, mock_makedirs, mock_open_func, mock_exec_scripts, 
                                 mock_validator, mock_loader, mock_o_extractor, 
                                 mock_ddl_gen, mock_s_extractor, mock_o_conn, mock_p_conn):
        
        # Setup mocks
        mock_validator_instance = mock_validator.return_value
        mock_validator_instance.validate_row_counts.return_value = True
        mock_validator_instance.validate_null_mismatches.return_value = True
        mock_validator_instance.validate_datatype_mismatches.return_value = True
        mock_validator_instance.validate_checksums.return_value = True
        
        mock_loader_instance = mock_loader.return_value
        mock_loader_instance.load_table.return_value = 500  # simulated rows inserted
        
        # Execute main with dummy args
        test_args = ["main.py", "--output-dir", "test_output", "--batch-size", "100"]
        with patch('sys.argv', test_args):
            main.main()
            
        # Assertions
        mock_o_conn.assert_called_once()
        mock_p_conn.assert_called_once()
        mock_s_extractor.assert_called_once()
        mock_ddl_gen.assert_called_once()
        mock_exec_scripts.assert_called_once()
        mock_o_extractor.assert_called_once()
        mock_loader.assert_called_once()
        mock_validator.assert_called_once()
        
        # Ensure validator was called correctly on the table
        mock_validator_instance.validate_row_counts.assert_called_with("TEST_TABLE")
        mock_validator_instance.validate_null_mismatches.assert_called_with("TEST_TABLE", ["ID"])
        mock_validator_instance.validate_checksums.assert_called_with("TEST_TABLE", ["ID"], ["ID"])
        
if __name__ == "__main__":
    unittest.main()
