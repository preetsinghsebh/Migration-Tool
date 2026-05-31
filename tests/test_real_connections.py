import sys
import os
import logging
from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import setup_logging
from connectors.oracle import OracleConnector
from connectors.postgres import PostgresConnector

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=== Starting Real Database Connection Validation ===")

    # Load from .env explicitly
    load_dotenv()

    oracle_user = os.getenv("ORACLE_USER")
    oracle_pass = os.getenv("ORACLE_PASSWORD")
    oracle_dsn = os.getenv("ORACLE_DSN")

    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_dbname = os.getenv("PG_DB")
    pg_user = os.getenv("PG_USER")
    pg_pass = os.getenv("PG_PASSWORD")

    logger.info(f"Connecting to Oracle (DSN: {oracle_dsn}, User: {oracle_user})...")
    oracle_conn = OracleConnector(oracle_user, oracle_pass, oracle_dsn)
    try:
        oracle_conn.initialize_pool()
        with oracle_conn.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 'Connection OK' FROM DUAL")
                res = cursor.fetchone()
                logger.info(f"Oracle Connection: SUCCESS ({res[0]})")
    except Exception as e:
        logger.error(f"Oracle Connection FAILED: {e}")
    finally:
        try:
            oracle_conn.close_pool()
        except Exception:
            pass

    logger.info(f"Connecting to PostgreSQL (Host: {pg_host}:{pg_port}, DB: {pg_dbname}, User: {pg_user})...")
    pg_conn = PostgresConnector(pg_host, pg_port, pg_dbname, pg_user, pg_pass)
    try:
        pg_conn.initialize_pool()
        with pg_conn.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 'Connection OK'")
                res = cursor.fetchone()
                logger.info(f"PostgreSQL Connection: SUCCESS ({res[0]})")
    except Exception as e:
        logger.error(f"PostgreSQL Connection FAILED: {e}")
    finally:
        try:
            pg_conn.close_pool()
        except Exception:
            pass

if __name__ == "__main__":
    main()
