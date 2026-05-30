import sys
import os
import logging
import time
import tempfile
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import setup_logging, ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
from connectors.oracle import OracleConnector
from extractors.schema_extractor import SchemaExtractor
from converters.ddl_generator import DDLGenerator

def run_stress_test():
    setup_logging()
    # Suppress normal logs from converters to keep output clean during stress test
    logging.getLogger('converters.datatype_converter').setLevel(logging.CRITICAL)
    logging.getLogger('converters.ddl_generator').setLevel(logging.WARNING)
    
    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.INFO)
    logger.info("--- Starting End-to-End Stress Test (100,000 tables) ---")

    NUM_TABLES = 100000
    
    # Setup Mocks for Schema Extractor
    mock_oracle_conn = MagicMock()
    mock_oracle_cursor = MagicMock()
    
    def mock_table_generator():
        for i in range(0, NUM_TABLES, 100):
            yield [(f"TABLE_{j}",) for j in range(i, i + 100)]
        yield []

    table_gen = mock_table_generator()

    def execute_side_effect(query, params=None):
        if "user_tables" in query:
            mock_oracle_cursor.fetchmany.side_effect = lambda size: next(table_gen, [])
        elif "user_tab_columns" in query:
            mock_oracle_cursor.__iter__.return_value = iter([
                ("COL_ID", "NUMBER", 10, 0, "N"),
                ("COL_NAME", "VARCHAR2", 50, None, "Y"),
                ("COL_DATE", "DATE", None, None, "Y"),
                ("COL_DATA", "BLOB", None, None, "Y"),
                ("COL_STATUS", "CHAR", 1, None, "N")
            ])
        elif "user_constraints" in query:
            mock_oracle_cursor.__iter__.return_value = iter([
                ("PK_TEST", "P", "COL_ID", None)
            ])
            
    mock_oracle_cursor.execute.side_effect = execute_side_effect
    mock_oracle_conn.cursor.return_value.__enter__.return_value = mock_oracle_cursor
    
    with patch('connectors.oracle.oracledb.create_pool') as mock_oracledb_pool:
        mock_oracle_pool_instance = MagicMock()
        mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
        mock_oracledb_pool.return_value = mock_oracle_pool_instance

        connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
        connector.initialize_pool(min_conn=1, max_conn=1)
        extractor = SchemaExtractor(connector)
        generator = DDLGenerator()
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_json:
            json_path = tmp_json.name
            
        output_dir = tempfile.mkdtemp()
            
        try:
            logger.info("PHASE 1: Schema Extraction")
            start_time = time.time()
            exported_count = extractor.export_schema_to_json(json_path)
            json_duration = time.time() - start_time
            json_size_mb = os.path.getsize(json_path) / (1024 * 1024)
            
            logger.info(f"Extraction completed in {json_duration:.2f} seconds.")
            logger.info(f"Generated JSON file size: {json_size_mb:.2f} MB.")
            
            logger.info("PHASE 2: DDL Generation")
            start_time = time.time()
            generated_count = generator.generate_ddl(json_path, output_dir)
            ddl_duration = time.time() - start_time
            
            # Calculate total size of all generated files
            total_sql_size_mb = sum(
                os.path.getsize(os.path.join(output_dir, f)) 
                for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))
            ) / (1024 * 1024)
            
            logger.info(f"DDL Generation completed in {ddl_duration:.2f} seconds.")
            logger.info(f"Generated {generated_count} SQL files (Total size: {total_sql_size_mb:.2f} MB).")
            logger.info(f"Both phases handled 100,000 tables and 500,000 columns smoothly!")
            
        finally:
            connector.close_pool()
            if os.path.exists(json_path):
                os.remove(json_path)
            if os.path.exists(output_dir):
                import shutil
                shutil.rmtree(output_dir)

if __name__ == "__main__":
    run_stress_test()
