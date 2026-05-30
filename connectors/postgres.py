import psycopg2
from psycopg2 import pool
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class PostgresConnector:
    """
    Enterprise-style database connector for PostgreSQL using connection pooling.
    """
    def __init__(self, host, port, dbname, user, password):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.pool = None

    def initialize_pool(self, min_conn=1, max_conn=5):
        """Initializes the psycopg2 connection pool."""
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password
            )
            logger.info("PostgreSQL connection pool initialized successfully.")
        except psycopg2.DatabaseError as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Context manager to safely acquire and release Postgres connections from the pool."""
        if not self.pool:
            raise RuntimeError("PostgreSQL connection pool is not initialized. Call initialize_pool() first.")
        
        connection = None
        try:
            connection = self.pool.getconn()
            yield connection
        except psycopg2.DatabaseError as e:
            logger.error(f"PostgreSQL connection error during operation: {e}")
            raise
        finally:
            if connection:
                self.pool.putconn(connection)

    def close_pool(self):
        """Gracefully closes the connection pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("PostgreSQL connection pool closed.")
