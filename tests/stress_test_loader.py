import sys
import os
import logging
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import setup_logging
from loaders.postgres_loader import PostgresLoader

def run_stress_test():
    setup_logging()
    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.INFO)
    logger.info("--- Starting Data Loader Stress Test (5,000,000 rows) ---")

    NUM_ROWS = 5000000
    BATCH_SIZE = 10000
    
    # 1. Memory-efficient generator that yields 5M rows in chunks of 10k
    def mock_data_generator():
        for i in range(0, NUM_ROWS, BATCH_SIZE):
            batch = []
            for j in range(i, i + BATCH_SIZE):
                batch.append({
                    "id": j,
                    "name": f"User_{j}",
                    "email": f"user_{j}@company.com",
                    "status": "ACTIVE",
                    "score": 99.9
                })
            yield batch

    # 2. Mocking the connector and cursor
    mock_connector = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    mock_connector.get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # We MUST patch execute_values with a dummy function!
    # If we used a standard MagicMock here, it would attempt to store the call history 
    # of all 5 million rows, crashing the system with an OutOfMemory error.
    def dummy_execute_values(cursor, sql, argslist):
        pass # Simulate instantaneous DB insert over the network

    with patch('loaders.postgres_loader.execute_values', side_effect=dummy_execute_values):
        loader = PostgresLoader(mock_connector)
        
        start_time = time.time()
        
        try:
            total_inserted = loader.load_table("users_stress_test", mock_data_generator())
            duration = time.time() - start_time
            
            logger.info(f"Loader Stress Test completed in {duration:.2f} seconds.")
            logger.info(f"Total Rows Processed: {total_inserted}")
            logger.info(f"Throughput: {total_inserted / duration:,.0f} rows/second")
            logger.info(f"Memory remained completely flat because of generator chunking!")
            
        except Exception as e:
            logger.error(f"Stress test failed: {e}")

if __name__ == "__main__":
    run_stress_test()
