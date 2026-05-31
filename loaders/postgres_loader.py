import logging
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

class PostgresLoader:
    """
    Handles bulk loading of data into PostgreSQL using memory-efficient batching.
    """
    def __init__(self, connector):
        """
        Initializes the loader with a PostgreSQL connection pool wrapper.
        """
        self.connector = connector

    def load_table(self, table_name, data_generator):
        """
        Loads data from a generator into the specified PostgreSQL table.
        The data_generator should yield lists of dictionaries (batches).
        
        Args:
            table_name (str): The destination PostgreSQL table name.
            data_generator (generator): A generator yielding lists of dictionaries.
            
        Returns:
            int: The total number of rows inserted.
        """
        total_rows_inserted = 0
        
        logger.info(f"Starting data load for table: {table_name}")
        
        # We acquire a single connection from the pool for the entire table load 
        # to handle it as a single transaction (or we could commit periodically).
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    for batch_idx, batch in enumerate(data_generator):
                        if not batch:
                            continue
                            
                        # Extract column names from the first row of the batch
                        columns = list(batch[0].keys())
                        
                        columns_str = ", ".join(f'"{col}"' for col in columns)
                        
                        # Build the INSERT statement template required by execute_values
                        insert_query = f'INSERT INTO "{table_name}" ({columns_str}) VALUES %s'
                        
                        # Convert dictionaries to tuples of values in the correct order
                        values = [[row.get(col) for col in columns] for row in batch]
                        
                        # Execute the bulk insert (psycopg2 handles the fast %s mapping automatically)
                        execute_values(cursor, insert_query, values)
                        
                        rows_in_batch = len(batch)
                        total_rows_inserted += rows_in_batch
                        logger.debug(f"Inserted batch {batch_idx + 1} ({rows_in_batch} rows). Total: {total_rows_inserted}")
                        
                    # Commit transaction after all batches are processed successfully
                    conn.commit()
                    logger.info(f"Successfully loaded {total_rows_inserted} rows into {table_name}.")
                    
                except Exception as e:
                    # Rollback the entire table transaction on error to prevent partial loads
                    conn.rollback()
                    logger.error(f"Failed to load data into {table_name}. Transaction rolled back. Error: {e}")
                    raise
                    
        return total_rows_inserted
