import logging

logger = logging.getLogger(__name__)

class OracleExtractor:
    """
    Extracts data from an Oracle database efficiently using pagination/chunking.
    """
    def __init__(self, connector):
        """
        Takes an instance of OracleConnector to manage database connections safely.
        """
        self.connector = connector

    def extract_table(self, table_name, batch_size=10000):
        """
        Yields rows from a specific table in chunks to prevent memory overload.
        """
        # Note: In a production environment, avoid simple string interpolation for table names 
        # to prevent SQL injection if table_name comes from user input. 
        # Assuming table_name is verified.
        query = f"SELECT * FROM {table_name}"
        yield from self.execute_query(query, batch_size=batch_size)

    def execute_query(self, query, batch_size=10000, params=None):
        """
        Executes a custom query and yields results in batches as a list of dictionaries.
        This uses a generator (yield) so it doesn't load millions of rows into RAM at once.
        """
        if params is None:
            params = {}

        logger.info(f"Starting data extraction | Batch Size: {batch_size} | Query: {query[:100]}...")
        
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, params)
                    
                    # Extract column names from the cursor description to convert tuples to dictionaries
                    columns = [col[0].lower() for col in cursor.description] if cursor.description else []
                    
                    batch_num = 1
                    while True:
                        rows = cursor.fetchmany(batch_size)
                        if not rows:
                            break
                        
                        # Convert list of tuples into list of dictionaries mapping column name to value
                        dict_rows = [dict(zip(columns, row)) for row in rows]
                        
                        logger.debug(f"Extracted batch {batch_num} with {len(dict_rows)} rows.")
                        yield dict_rows
                        batch_num += 1
                        
                except Exception as e:
                    logger.error(f"Error executing extraction query: {e}")
                    raise
                    
        logger.info("Data extraction completed successfully.")

    def get_tables(self):
        """
        Retrieves a list of all tables owned by the current user.
        """
        query = "SELECT table_name FROM user_tables"
        logger.info("Extracting tables from user_tables...")
        
        tables = []
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                for row in cursor:
                    tables.append(row[0])
        return tables

    def get_columns(self, table_name=None):
        """
        Retrieves column metadata (name, datatype, etc.) for a specific table or all tables.
        """
        query = """
            SELECT table_name, column_name, data_type, data_length, 
                   data_precision, data_scale, nullable 
            FROM user_tab_columns
        """
        params = []
        if table_name:
            query += " WHERE table_name = :1"
            params.append(table_name)
            
        logger.info(f"Extracting columns... (table: {table_name or 'ALL'})")
        
        columns_by_table = {}
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                for row in cursor:
                    t_name, c_name, d_type, d_len, d_prec, d_scale, nullable = row
                    if t_name not in columns_by_table:
                        columns_by_table[t_name] = []
                    
                    columns_by_table[t_name].append({
                        "column_name": c_name,
                        "data_type": d_type,
                        "data_length": d_len,
                        "data_precision": d_prec,
                        "data_scale": d_scale,
                        "nullable": True if nullable == 'Y' else False
                    })
        return columns_by_table

    def get_constraints(self, table_name=None):
        """
        Retrieves constraints (Primary Key, Foreign Key, Unique) for tables.
        """
        query = """
            SELECT c.table_name, c.constraint_name, c.constraint_type, 
                   cc.column_name, c.r_constraint_name
            FROM user_constraints c
            JOIN user_cons_columns cc ON c.constraint_name = cc.constraint_name
            WHERE c.constraint_type IN ('P', 'R', 'U')
        """
        params = []
        if table_name:
            query += " AND c.table_name = :1"
            params.append(table_name)
            
        logger.info(f"Extracting constraints... (table: {table_name or 'ALL'})")
        
        constraints_by_table = {}
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                for row in cursor:
                    t_name, cons_name, cons_type, col_name, r_cons_name = row
                    
                    if t_name not in constraints_by_table:
                        constraints_by_table[t_name] = {}
                        
                    if cons_name not in constraints_by_table[t_name]:
                        constraints_by_table[t_name][cons_name] = {
                            "type": cons_type, # P=Primary Key, R=Foreign Key, U=Unique
                            "columns": [],
                            "r_constraint_name": r_cons_name
                        }
                    
                    constraints_by_table[t_name][cons_name]["columns"].append(col_name)
                    
        return constraints_by_table

    def extract_schema(self, table_names=None):
        """
        Convenience method to extract the full schema (tables, columns, constraints).
        If table_names is provided, limits extraction to those tables.
        """
        schema = {}
        
        if table_names is None:
            tables = self.get_tables()
        else:
            tables = table_names
            
        for table in tables:
            schema[table] = {
                "columns": self.get_columns(table).get(table, []),
                "constraints": self.get_constraints(table).get(table, {})
            }
            
        return schema
