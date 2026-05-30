import oracledb
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class OracleConnector:
    """
    Enterprise-style database connector for Oracle using connection pooling.
    """
    def __init__(self, username, password, dsn):
        self.username = username
        self.password = password
        self.dsn = dsn
        self.pool = None

    def initialize_pool(self, min_conn=1, max_conn=5, increment=1):
        """Initializes the oracledb connection pool."""
        try:
            self.pool = oracledb.create_pool(
                user=self.username,
                password=self.password,
                dsn=self.dsn,
                min=min_conn,
                max=max_conn,
                increment=increment
            )
            logger.info("Oracle connection pool initialized successfully.")
        except oracledb.DatabaseError as e:
            logger.error(f"Failed to initialize Oracle pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Context manager to safely acquire and release Oracle connections from the pool."""
        if not self.pool:
            raise RuntimeError("Oracle connection pool is not initialized. Call initialize_pool() first.")
        
        connection = None
        try:
            connection = self.pool.acquire()
            yield connection
        except oracledb.DatabaseError as e:
            logger.error(f"Oracle connection error during operation: {e}")
            raise
        finally:
            if connection:
                self.pool.release(connection)

    def close_pool(self):
        """Gracefully closes the connection pool."""
        if self.pool:
            self.pool.close()
            logger.info("Oracle connection pool closed.")
