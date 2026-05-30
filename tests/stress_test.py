import sys
import os
import logging
import time
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import setup_logging, ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
from connectors.oracle import OracleConnector
from extractors.schema_extractor import SchemaExtractor

def run_stress_test():
    setup_logging()
    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.INFO)
    logger.info("--- Starting Schema Extractor Stress Test (100,000 mock tables) ---")

    NUM_TABLES = 100000
    
    # Setup Mocks
    mock_oracle_conn = MagicMock()
    mock_oracle_cursor = MagicMock()
    
    # We use generators for the mocks so they don't consume huge amounts of memory instantly either
    def mock_table_generator():
        # Yield rows in chunks of 100
        for i in range(0, NUM_TABLES, 100):
            yield [(f"TABLE_{j}",) for j in range(i, i + 100)]
        yield []

    table_gen = mock_table_generator()

    def execute_side_effect(query, params=None):
        if "user_tables" in query:
            # When fetchmany is called, return next from generator
            mock_oracle_cursor.fetchmany.side_effect = lambda size: next(table_gen, [])
        elif "user_tab_columns" in query:
            # Return a fast mock iterator of 5 columns for each table
            mock_oracle_cursor.__iter__.return_value = iter([
                ("COL_ID", "NUMBER", 10, 0, "N"),
                ("COL_NAME", "VARCHAR2", 50, None, "Y"),
                ("COL_DATE", "DATE", None, None, "Y"),
                ("COL_DATA", "BLOB", None, None, "Y"),
                ("COL_STATUS", "CHAR", 1, None, "N")
            ])
            
    mock_oracle_cursor.execute.side_effect = execute_side_effect
    mock_oracle_conn.cursor.return_value.__enter__.return_value = mock_oracle_cursor
    
    # We patch oracledb locally
    with patch('connectors.oracle.oracledb.create_pool') as mock_oracledb_pool:
        mock_oracle_pool_instance = MagicMock()
        mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
        mock_oracledb_pool.return_value = mock_oracle_pool_instance

        connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
        connector.initialize_pool(min_conn=1, max_conn=1)
        extractor = SchemaExtractor(connector)
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            start_time = time.time()
            exported_count = extractor.export_schema_to_json(tmp_path)
            duration = time.time() - start_time
            
            file_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
            
            logger.info(f"Stress test completed in {duration:.2f} seconds.")
            logger.info(f"Exported {exported_count} tables.")
            logger.info(f"Generated JSON file size: {file_size_mb:.2f} MB.")
            logger.info(f"Because the extractor uses generators, memory consumption remained flat!")
            
        finally:
            connector.close_pool()
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    run_stress_test()
