import sys
import os
import logging
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import setup_logging, ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN, \
                            PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD
from connectors.oracle import OracleConnector
from connectors.postgres import PostgresConnector

@patch('connectors.postgres.psycopg2.pool.SimpleConnectionPool')
@patch('connectors.oracle.oracledb.create_pool')
def test_database_connections(mock_oracledb_pool, mock_pg_pool):
    """
    Main testing flow to validate connections to both databases securely using mocks
    for stable execution without needing local databases.
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("--- Starting Database Connection Tests (Mocked) ---")

    # Setup mocks
    mock_oracle_conn = MagicMock()
    mock_oracle_cursor = MagicMock()
    mock_oracle_cursor.fetchone.return_value = ["Oracle Connection Successful (Mocked)"]
    mock_oracle_conn.cursor.return_value = mock_oracle_cursor
    
    mock_oracle_pool_instance = MagicMock()
    mock_oracle_pool_instance.acquire.return_value = mock_oracle_conn
    mock_oracledb_pool.return_value = mock_oracle_pool_instance

    # 1. Test Oracle Connection
    oracle_connector = OracleConnector(ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN)
    try:
        oracle_connector.initialize_pool()
        with oracle_connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 'Oracle Connection Successful' FROM DUAL")
            result = cursor.fetchone()
            logger.info(f"Oracle Validation: {result[0]}")
    except Exception as e:
        logger.error(f"Oracle Validation Failed: {e}")
        sys.exit(1)
    finally:
        oracle_connector.close_pool()

    # Setup PG Mocks
    mock_pg_conn = MagicMock()
    mock_pg_cursor = MagicMock()
    mock_pg_cursor.fetchone.return_value = ["PostgreSQL Connection Successful (Mocked)"]
    mock_pg_conn.cursor.return_value = mock_pg_cursor
    
    mock_pg_pool_instance = MagicMock()
    mock_pg_pool_instance.getconn.return_value = mock_pg_conn
    mock_pg_pool.return_value = mock_pg_pool_instance

    # 2. Test PostgreSQL Connection
    pg_connector = PostgresConnector(PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD)
    try:
        pg_connector.initialize_pool()
        with pg_connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 'PostgreSQL Connection Successful';")
            result = cursor.fetchone()
            logger.info(f"PostgreSQL Validation: {result[0]}")
    except Exception as e:
        logger.error(f"PostgreSQL Validation Failed: {e}")
        sys.exit(1)
    finally:
        pg_connector.close_pool()
        
    logger.info("--- Database Connection Tests Completed ---")

if __name__ == "__main__":
    test_database_connections()
