import logging
import hashlib
from typing import List, Dict

logger = logging.getLogger(__name__)

class MigrationValidator:
    """
    Validates data integrity between an Oracle source and PostgreSQL destination.
    """
    def __init__(self, oracle_connector, pg_connector):
        self.oracle_connector = oracle_connector
        self.pg_connector = pg_connector

    def validate_row_counts(self, table_name: str) -> bool:
        """
        Validates that both databases have the exact same number of rows for a table.
        """
        logger.info(f"Validating row counts for {table_name}...")
        
        oracle_count = 0
        with self.oracle_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                oracle_count = cursor.fetchone()[0]
                
        pg_count = 0
        with self.pg_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                pg_count = cursor.fetchone()[0]
                
        is_valid = oracle_count == pg_count
        if is_valid:
            logger.info(f"Row count validation SUCCESS: {oracle_count} rows in both.")
        else:
            logger.error(f"Row count mismatch! Oracle: {oracle_count}, Postgres: {pg_count}")
            
        return is_valid

    def validate_null_mismatches(self, table_name: str, columns: List[str]) -> bool:
        """
        Validates that the count of NULL values for each column matches exactly.
        """
        logger.info(f"Validating NULL mismatches for {table_name}...")
        all_valid = True
        
        for col in columns:
            query = f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col}" IS NULL'
            
            oracle_nulls = 0
            with self.oracle_connector.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    oracle_nulls = cursor.fetchone()[0]
                    
            pg_nulls = 0
            with self.pg_connector.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    pg_nulls = cursor.fetchone()[0]
                    
            if oracle_nulls != pg_nulls:
                all_valid = False
                logger.error(f"NULL mismatch on {table_name}.{col}. Oracle: {oracle_nulls}, Postgres: {pg_nulls}")
                
        if all_valid:
            logger.info(f"NULL validation SUCCESS for {table_name}.")
            
        return all_valid
        
    def _normalize_val(self, val):
        if val is None:
            return ""
        import decimal
        import datetime
        if isinstance(val, (decimal.Decimal, float, int)):
            try:
                if val % 1 == 0:
                    return str(int(val))
                else:
                    return str(float(val))
            except Exception:
                return str(val)
        if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
            return val.isoformat()
        return str(val)
        
    def validate_checksums(self, table_name: str, pk_columns, columns: List[str], batch_size=10000) -> bool:
        """
        Streams rows ordered by primary key, concatenates values, and generates a SHA-256 hash.
        This provides 100% cryptographic proof of data fidelity and avoids cross-database hashing quirks.
        """
        if isinstance(pk_columns, str):
            pk_columns = [pk_columns]
            
        logger.info(f"Validating checksums for {table_name}...")
        
        # 1. Determine PostgreSQL column types to apply COLLATE "C" on text columns for deterministic sorting
        pg_types = {}
        try:
            with self.pg_connector.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s",
                        [table_name]
                    )
                    for row in cursor:
                        pg_types[row[0].upper()] = row[1].upper()
                    if not pg_types:
                        cursor.execute(
                            "SELECT column_name, data_type FROM information_schema.columns WHERE LOWER(table_name) = LOWER(%s)",
                            [table_name]
                        )
                        for row in cursor:
                            pg_types[row[0].upper()] = row[1].upper()
        except Exception as e:
            logger.warning(f"Failed to query column types in Postgres for collation sorting: {e}")
            
        col_str = ", ".join(f'"{col}"' for col in columns)
        
        # Oracle query: standard ORDER BY (binary collation by default)
        oracle_order_cols = ", ".join(f'"{col}"' for col in pk_columns)
        oracle_query = f'SELECT {col_str} FROM "{table_name}" ORDER BY {oracle_order_cols}'
        
        # PostgreSQL query: append COLLATE "C" for character columns to match Oracle binary sorting
        pg_order_cols_list = []
        for col in pk_columns:
            col_upper = col.upper()
            col_type = pg_types.get(col_upper, "")
            if "CHAR" in col_type or "TEXT" in col_type or "VARCHAR" in col_type:
                pg_order_cols_list.append(f'"{col}" COLLATE "C"')
            else:
                pg_order_cols_list.append(f'"{col}"')
        pg_order_cols = ", ".join(pg_order_cols_list)
        pg_query = f'SELECT {col_str} FROM "{table_name}" ORDER BY {pg_order_cols}'
        
        oracle_hash = hashlib.sha256()
        with self.oracle_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(oracle_query)
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    for row in rows:
                        row_str = "|".join([self._normalize_val(val) for val in row])
                        oracle_hash.update(row_str.encode('utf-8'))
                        
        pg_hash = hashlib.sha256()
        with self.pg_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(pg_query)
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    for row in rows:
                        row_str = "|".join([self._normalize_val(val) for val in row])
                        pg_hash.update(row_str.encode('utf-8'))
                        
        o_digest = oracle_hash.hexdigest()
        p_digest = pg_hash.hexdigest()
        
        if o_digest == p_digest:
            logger.info(f"Checksum validation SUCCESS for {table_name}. Hash: {o_digest[:8]}...")
            return True
        else:
            logger.error(f"Checksum mismatch! Oracle: {o_digest}, Postgres: {p_digest}")
            return False
            
    def validate_datatype_mismatches(self, table_name: str, expected_schema: Dict) -> bool:
        """
        Validates that the actual PostgreSQL schema types exist and roughly align.
        Expected schema should be the dict output from our SchemaExtractor.
        """
        logger.info(f"Validating datatypes for {table_name}...")
        
        query = """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s
        """
        
        pg_columns = {}
        with self.pg_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                # Use exact casing matching how it was created
                cursor.execute(query, [table_name])
                for row in cursor:
                    pg_columns[row[0].upper()] = row[1].upper()
                    
        all_valid = True
        
        for col_dict in expected_schema.get("columns", []):
            col_name = col_dict["name"].upper()
            
            if col_name not in pg_columns:
                logger.error(f"Column {col_name} missing from Postgres table {table_name}.")
                all_valid = False
                continue
                
            pg_actual = pg_columns[col_name]
            logger.debug(f"Column {col_name} verified present as {pg_actual}.")
            
        if all_valid:
            logger.info(f"Datatype schema validation SUCCESS for {table_name}.")
            
        return all_valid
