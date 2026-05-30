import sys
import os
import logging
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import setup_logging, ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
from connectors.oracle import OracleConnector
from extractors.oracle_extractor import OracleExtractor

@patch('connectors.oracle.oracledb.create_pool')
def test_extraction(mock_oracledb_pool):
    """
    Testing flow to validate data extraction in batches using mocks for stable execution.
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("--- Starting Extractor Module Test (Mocked) ---")

    # Setup Oracle Mocks to return exactly 3 rows
    mock_oracle_conn = MagicMock()
    mock_oracle_cursor = MagicMock()
    
    # Mock description (column names)
    mock_oracle_cursor.description = [('USERNAME',), ('USER_ID',), ('CREATED',)]
    
    # Mock fetchmany to return 2 rows on first call, 1 row on second, 0 on third
    mock_oracle_cursor.fetchmany.side_effect = [
        [('ADMIN', 1, '2023-01-01'), ('USER1', 2, '2023-01-02')],
        [('USER2', 3, '2023-01-03')],
        []
    ]
    mock_oracle_conn.cursor.return_value.__enter__.return_value = mock_oracle_cursor
    
    mock_oracle_pool_instance = MagicMock()
    mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
    mock_oracledb_pool.return_value = mock_oracle_pool_instance

    # 1. Initialize Connector
    connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
    
    try:
        connector.initialize_pool(min_conn=1, max_conn=2)
        
        # 2. Initialize Extractor
        extractor = OracleExtractor(connector)
        
        query = "SELECT username, user_id, created FROM all_users WHERE ROWNUM <= 5"
        logger.info("Testing extraction using a sample query...")
        
        batch_count = 0
        total_rows = 0
        
        for batch in extractor.execute_query(query, batch_size=2):
            batch_count += 1
            total_rows += len(batch)
            logger.info(f"Received Batch {batch_count}: {len(batch)} rows.")
            for row in batch:
                logger.info(f"Row Data: {row}")
                
        logger.info(f"Extraction successful. Total batches: {batch_count}, Total rows: {total_rows}")

        # Assertions to guarantee stable logic
        assert batch_count == 2, "Should have 2 batches"
        assert total_rows == 3, "Should have exactly 3 rows total"

    except Exception as e:
        logger.error(f"Extractor Test Failed: {e}")
        sys.exit(1)
    finally:
        connector.close_pool()
        
    logger.info("--- Extractor Module Test Completed ---")

@patch('connectors.oracle.oracledb.create_pool')
def test_schema_extraction(mock_oracledb_pool):
    """
    Test the schema extraction methods (tables, columns, constraints) using mocks.
    """
    logger = logging.getLogger(__name__)
    logger.info("--- Starting Schema Extraction Test (Mocked) ---")

    # Mock the connection and cursor
    mock_oracle_conn = MagicMock()
    mock_oracle_cursor = MagicMock()
    
    # We will mock the cursor as an iterator for fetchall/for loops
    # but since it uses `for row in cursor`, we need `__iter__` on cursor to return rows.
    mock_oracle_conn.cursor.return_value.__enter__.return_value = mock_oracle_cursor
    
    mock_oracle_pool_instance = MagicMock()
    mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
    mock_oracledb_pool.return_value = mock_oracle_pool_instance

    connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
    try:
        connector.initialize_pool(min_conn=1, max_conn=1)
        extractor = OracleExtractor(connector)

        # 1. Test get_tables
        mock_oracle_cursor.__iter__.return_value = [("USERS",), ("ORDERS",)]
        tables = extractor.get_tables()
        assert len(tables) == 2
        assert "USERS" in tables
        assert "ORDERS" in tables
        logger.info("get_tables() passed.")

        # 2. Test get_columns
        mock_oracle_cursor.__iter__.return_value = [
            ("USERS", "ID", "NUMBER", 22, 10, 0, "N"),
            ("USERS", "USERNAME", "VARCHAR2", 50, None, None, "Y")
        ]
        columns = extractor.get_columns("USERS")
        assert "USERS" in columns
        assert len(columns["USERS"]) == 2
        assert columns["USERS"][0]["column_name"] == "ID"
        assert columns["USERS"][1]["data_type"] == "VARCHAR2"
        logger.info("get_columns() passed.")

        # 3. Test get_constraints
        mock_oracle_cursor.__iter__.return_value = [
            ("USERS", "PK_USERS", "P", "ID", None),
            ("USERS", "UQ_USERNAME", "U", "USERNAME", None)
        ]
        constraints = extractor.get_constraints("USERS")
        assert "USERS" in constraints
        assert "PK_USERS" in constraints["USERS"]
        assert constraints["USERS"]["PK_USERS"]["type"] == "P"
        assert "ID" in constraints["USERS"]["PK_USERS"]["columns"]
        logger.info("get_constraints() passed.")

    except Exception as e:
        logger.error(f"Schema Extractor Test Failed: {e}")
        sys.exit(1)
    finally:
        connector.close_pool()
        
    logger.info("--- Schema Extraction Test Completed ---")

if __name__ == "__main__":
    test_extraction()
    test_schema_extraction()
