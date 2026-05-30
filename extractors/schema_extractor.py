import logging
from utils.json_utils import write_json_iteratively

logger = logging.getLogger(__name__)

class SchemaExtractor:
    """
    Extracts schema metadata (tables, columns, datatypes) from an Oracle database.
    Designed for memory efficiency when dealing with large schemas.
    """
    def __init__(self, connector):
        self.connector = connector

    def get_tables_generator(self):
        """
        Yields table names one by one directly from the database cursor
        to prevent keeping a massive list of table names in memory.
        """
        query = "SELECT table_name FROM user_tables"
        logger.info("Initializing extraction of table names from user_tables...")
        
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query)
                    while True:
                        # Fetching in small batches for memory safety, yielding one by one
                        rows = cursor.fetchmany(100)
                        if not rows:
                            break
                        for row in rows:
                            yield row[0]
                except Exception as e:
                    logger.error(f"Error extracting tables: {e}")
                    raise

    def get_table_columns(self, table_name):
        """
        Retrieves column metadata (name and datatype) for a specific table.
        """
        query = """
            SELECT column_name, data_type, data_precision, data_scale, nullable
            FROM user_tab_columns
            WHERE table_name = :1
        """
        
        columns = []
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, [table_name])
                    for row in cursor:
                        col_name, d_type, d_prec, d_scale, nullable = row
                        columns.append({
                            "name": col_name,
                            "datatype": d_type,
                            "precision": d_prec,
                            "scale": d_scale,
                            "nullable": True if nullable == 'Y' else False
                        })
                except Exception as e:
                    logger.error(f"Error extracting columns for table {table_name}: {e}")
                    raise
                    
        return columns

    def get_table_constraints(self, table_name):
        """
        Retrieves constraints (Primary Key, Foreign Key, Unique) for a specific table.
        """
        query = """
            SELECT c.constraint_name, c.constraint_type, 
                   cc.column_name, c.r_constraint_name
            FROM user_constraints c
            JOIN user_cons_columns cc ON c.constraint_name = cc.constraint_name
            WHERE c.constraint_type IN ('P', 'R', 'U') AND c.table_name = :1
        """
        
        constraints = {}
        with self.connector.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, [table_name])
                    for row in cursor:
                        cons_name, cons_type, col_name, r_cons_name = row
                        
                        if cons_name not in constraints:
                            constraints[cons_name] = {
                                "name": cons_name,
                                "type": cons_type, # P=Primary Key, R=Foreign Key, U=Unique
                                "columns": [],
                                "r_constraint_name": r_cons_name
                            }
                        
                        constraints[cons_name]["columns"].append(col_name)
                except Exception as e:
                    logger.error(f"Error extracting constraints for table {table_name}: {e}")
                    raise
                    
        return list(constraints.values())

    def _schema_generator(self, table_names=None):
        """
        Internal generator that yields the structured dictionary for each table.
        """
        # If no tables are provided, use the generator to get all tables safely
        tables = table_names if table_names else self.get_tables_generator()
        
        for table in tables:
            logger.debug(f"Extracting schema for table: {table}")
            columns = self.get_table_columns(table)
            constraints = self.get_table_constraints(table)
            
            yield {
                "table_name": table,
                "columns": columns,
                "constraints": constraints
            }

    def export_schema_to_json(self, output_file_path, table_names=None):
        """
        Extracts the schema and writes it iteratively to a JSON file.
        
        Args:
            output_file_path (str): The destination file path.
            table_names (list, optional): Specific tables to extract. Defaults to all tables.
            
        Returns:
            int: The number of tables extracted.
        """
        logger.info(f"Starting schema extraction to {output_file_path}")
        schema_gen = self._schema_generator(table_names)
        tables_exported = write_json_iteratively(output_file_path, schema_gen)
        logger.info(f"Schema extraction completed successfully. {tables_exported} tables exported.")
        return tables_exported
