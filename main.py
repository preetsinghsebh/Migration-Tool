import argparse
import logging
import time
import os
import glob
import json
import re

from config.settings import setup_logging
from connectors.oracle import OracleConnector
from connectors.postgres import PostgresConnector
from extractors.schema_extractor import SchemaExtractor
from extractors.oracle_extractor import OracleExtractor
from converters.ddl_generator import DDLGenerator
from loaders.postgres_loader import PostgresLoader
from validators.migration_validator import MigrationValidator

logger = logging.getLogger(__name__)

def execute_postgres_scripts(pg_connector, ddl_dir):
    """Executes generated sequences and table creation scripts against PostgreSQL."""
    logger.info(f"Deploying generated DDL schema scripts from {ddl_dir} to PostgreSQL...")
    
    # 1. Sequences script first
    sequences_sql = os.path.join(ddl_dir, "sequences.sql")
    # 2. Table creation scripts
    table_sql_files = glob.glob(os.path.join(ddl_dir, "tables", "*.sql"))
    
    order_of_execution = []
    if os.path.exists(sequences_sql):
        order_of_execution.append(sequences_sql)
        
    order_of_execution.extend(sorted(table_sql_files)) # Sort tables alphabetically
    
    with pg_connector.get_connection() as conn:
        with conn.cursor() as cursor:
            for sql_file in order_of_execution:
                logger.info(f"Executing {os.path.basename(sql_file)}...")
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                    if sql_content.strip():
                        try:
                            cursor.execute(sql_content)
                            conn.commit()
                        except Exception as e:
                            logger.error(f"Error executing script {sql_file}: {e}")
                            conn.rollback()
                            raise RuntimeError(f"Failed to execute SQL script: {sql_file}. Error: {e}")
    logger.info("Schema deployment completed.")

def execute_postgres_constraints(pg_connector, ddl_dir):
    """Executes foreign key constraint scripts against PostgreSQL."""
    constraints_sql = os.path.join(ddl_dir, "constraints.sql")
    if not os.path.exists(constraints_sql):
        logger.info("No constraints script found to deploy.")
        return
        
    logger.info(f"Deploying foreign key constraints from {constraints_sql} to PostgreSQL...")
    with pg_connector.get_connection() as conn:
        with conn.cursor() as cursor:
            logger.info("Executing constraints.sql...")
            with open(constraints_sql, 'r', encoding='utf-8') as f:
                sql_content = f.read()
                if sql_content.strip():
                    try:
                        cursor.execute(sql_content)
                        conn.commit()
                    except Exception as e:
                        logger.error(f"Error executing constraints script: {e}")
                        conn.rollback()
                        raise RuntimeError(f"Failed to execute constraints SQL script. Error: {e}")
    logger.info("Constraints deployment completed.")

def sync_postgres_sequences(pg_connector):
    """
    Finds all public table columns with nextval() default expressions,
    queries the max ID in the table, and aligns the sequence value to it.
    """
    logger.info("=== Starting Sequence Synchronization ===")
    
    # Query to find tables, columns and the sequence they default to
    query = """
        SELECT 
            t.relname AS table_name, 
            a.attname AS column_name, 
            pg_get_expr(d.adbin, d.adrelid) AS default_value
        FROM pg_attrdef d
        JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
        JOIN pg_class t ON t.oid = d.adrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public' 
          AND pg_get_expr(d.adbin, d.adrelid) LIKE '%nextval%';
    """
    
    with pg_connector.get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(query)
                defaults = cursor.fetchall()
            except Exception as e:
                logger.error(f"Failed to query database defaults for sequences: {e}")
                conn.rollback()
                return

            if not defaults:
                logger.info("No columns with sequence defaults found in Postgres.")
                return

            for table_name, column_name, default_expr in defaults:
                try:
                    match = re.search(r"nextval\('([^']+)'", default_expr)
                    if not match:
                        continue
                    seq_name = match.group(1)
                    
                    cursor.execute(f'SELECT COALESCE(MAX("{column_name}"), 0) FROM "{table_name}"')
                    max_val = cursor.fetchone()[0]
                    
                    if max_val > 0:
                        cursor.execute(f"SELECT setval(%s, %s, true)", [seq_name, max_val])
                        new_val = max_val + 1
                    else:
                        cursor.execute(f"SELECT setval(%s, 1, false)", [seq_name])
                        new_val = 1
                    
                    logger.info(f"Synchronized sequence '{seq_name}' for '{table_name}.{column_name}' to next value: {new_val}")
                except Exception as e:
                    logger.warning(f"Failed to sync sequence for table {table_name}.{column_name}: {e}")
                    conn.rollback()
            conn.commit()
    logger.info("Sequence synchronization completed successfully.")

def main():
    parser = argparse.ArgumentParser(description="Enterprise Oracle to PostgreSQL Migration Tool")
    parser.add_argument("--output-dir", default="output", help="Directory to store intermediate JSON and SQL files.")
    parser.add_argument("--batch-size", type=int, default=10000, help="Number of rows per batch extract/load.")
    args = parser.parse_args()

    setup_logging()
    logger.info("=== Starting Enterprise Migration Pipeline ===")
    
    os.makedirs(args.output_dir, exist_ok=True)
    json_schema_path = os.path.join(args.output_dir, "schema.json")
    ddl_output_dir = os.path.join(args.output_dir, "ddl")
    os.makedirs(ddl_output_dir, exist_ok=True)
    
    start_time = time.time()
    
    # 1. Initialize Connectors
    logger.info("Phase 0: Initializing database connections...")
    
    oracle_user = os.getenv("ORACLE_USER", "system")
    oracle_pass = os.getenv("ORACLE_PASSWORD", os.getenv("ORACLE_PASS", "password"))
    oracle_dsn = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")
    
    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_dbname = os.getenv("PG_DB", os.getenv("PG_DBNAME", "postgres"))
    pg_user = os.getenv("PG_USER", "postgres")
    pg_pass = os.getenv("PG_PASSWORD", os.getenv("PG_PASS", "password"))
    
    oracle_connector = OracleConnector(oracle_user, oracle_pass, oracle_dsn)
    pg_connector = PostgresConnector(pg_host, pg_port, pg_dbname, pg_user, pg_pass)
    
    try:
        oracle_connector.initialize_pool()
        pg_connector.initialize_pool()
        # 2. Extract Schema
        logger.info("\n=== Phase 1: Schema Extraction ===")
        schema_extractor = SchemaExtractor(oracle_connector)
        schema_extractor.export_schema_to_json(json_schema_path)
        
        json_sequences_path = os.path.join(args.output_dir, "sequences.json")
        schema_extractor.export_sequences_to_json(json_sequences_path)
        
        # 3. Generate DDL
        logger.info("\n=== Phase 2 & 3: Type Conversion & DDL Generation ===")
        ddl_generator = DDLGenerator()
        ddl_generator.generate_ddl(json_schema_path, ddl_output_dir)
        
        # 4. Deploy Schema to Postgres
        logger.info("\n=== Phase 4: Schema Deployment ===")
        execute_postgres_scripts(pg_connector, ddl_output_dir)
        
        # 5. Data Migration
        logger.info("\n=== Phase 5: Data Migration ===")
        oracle_extractor = OracleExtractor(oracle_connector)
        postgres_loader = PostgresLoader(pg_connector)
        
        with open(json_schema_path, 'r', encoding='utf-8') as f:
            schema_data = json.load(f)
            
        migration_stats = {}
        for table_dict in schema_data:
            table_name = table_dict["table_name"]
            logger.info(f"Migrating table: {table_name}")
            
            data_gen = oracle_extractor.extract_table(table_name, batch_size=args.batch_size)
            rows_inserted = postgres_loader.load_table(table_name, data_gen)
            migration_stats[table_name] = rows_inserted
            
        # 5.5. Sequence Syncing
        logger.info("\n=== Phase 5.5: Sequence Synchronization ===")
        sync_postgres_sequences(pg_connector)
        
        # 5.6. Deploy Constraints
        logger.info("\n=== Phase 5.6: Constraints Deployment ===")
        execute_postgres_constraints(pg_connector, ddl_output_dir)
            
        # 6. Validation
        logger.info("\n=== Phase 6: Data Validation ===")
        validator = MigrationValidator(oracle_connector, pg_connector)
        validation_failures = 0
        
        for table_dict in schema_data:
            table_name = table_dict["table_name"]
            pk_columns = []
            for constraint in table_dict.get("constraints", []):
                if constraint.get("type") == "P":
                    cols = constraint.get("columns", [])
                    if cols:
                        pk_columns = cols
                    else:
                        col_name = constraint.get("column_name")
                        if col_name:
                            pk_columns = [col_name]
                    break
            
            columns = [col["name"] for col in table_dict.get("columns", [])]
            
            if not validator.validate_row_counts(table_name):
                validation_failures += 1
            if not validator.validate_null_mismatches(table_name, columns):
                validation_failures += 1
            if not validator.validate_datatype_mismatches(table_name, table_dict):
                validation_failures += 1
            
            if pk_columns:
                if not validator.validate_checksums(table_name, pk_columns, columns):
                    validation_failures += 1
            else:
                logger.warning(f"Skipping checksum validation for {table_name} due to missing Primary Key.")
                
        # 7. Reporting
        logger.info("\n=== Phase 7: Migration Report ===")
        total_duration = time.time() - start_time
        total_rows = sum(migration_stats.values())
        
        logger.info(f"Total Migration Time: {total_duration:.2f} seconds")
        logger.info(f"Total Tables Migrated: {len(migration_stats)}")
        logger.info(f"Total Rows Migrated: {total_rows}")
        
        if validation_failures == 0:
            logger.info("MIGRATION STATUS: SUCCESS")
            logger.info("All validation checks passed with 100% integrity.")
        else:
            logger.error("MIGRATION STATUS: FAILED")
            logger.error(f"{validation_failures} validation checks failed. Please review the logs.")
            
    except Exception as e:
        logger.error(f"Migration aborted due to fatal error: {e}")
    finally:
        oracle_connector.close_pool()
        pg_connector.close_pool()

if __name__ == "__main__":
    main()
