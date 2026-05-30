import argparse
import logging
import time
import os
import glob
import json

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
    """Executes generated .sql files against PostgreSQL to create the schema."""
    logger.info(f"Deploying generated DDL scripts from {ddl_dir} to PostgreSQL...")
    sql_files = glob.glob(os.path.join(ddl_dir, "*.sql"))
    
    with pg_connector.get_connection() as conn:
        with conn.cursor() as cursor:
            for sql_file in sql_files:
                logger.info(f"Executing {os.path.basename(sql_file)}...")
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                    if sql_content.strip():
                        # A robust engine would split on semicolons, but for simple schemas this works
                        try:
                            cursor.execute(sql_content)
                        except Exception as e:
                            logger.warning(f"Error executing script {sql_file}: {e}")
                            conn.rollback()
                            continue
        conn.commit()
    logger.info("Schema deployment completed.")

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
    oracle_pass = os.getenv("ORACLE_PASS", "password")
    oracle_dsn = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")
    
    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_dbname = os.getenv("PG_DBNAME", "postgres")
    pg_user = os.getenv("PG_USER", "postgres")
    pg_pass = os.getenv("PG_PASS", "password")
    
    oracle_connector = OracleConnector(oracle_user, oracle_pass, oracle_dsn)
    pg_connector = PostgresConnector(pg_host, pg_port, pg_dbname, pg_user, pg_pass)
    
    try:
        oracle_connector.initialize_pool()
        pg_connector.initialize_pool()
        # 2. Extract Schema
        logger.info("\n=== Phase 1: Schema Extraction ===")
        schema_extractor = SchemaExtractor(oracle_connector)
        schema_extractor.export_schema_to_json(json_schema_path)
        
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
            
        # 6. Validation
        logger.info("\n=== Phase 6: Data Validation ===")
        validator = MigrationValidator(oracle_connector, pg_connector)
        validation_failures = 0
        
        for table_dict in schema_data:
            table_name = table_dict["table_name"]
            pk_column = None
            for constraint in table_dict.get("constraints", []):
                if constraint.get("type") == "P":
                    pk_column = constraint.get("column_name")
                    break
            
            columns = [col["name"] for col in table_dict.get("columns", [])]
            
            if not validator.validate_row_counts(table_name):
                validation_failures += 1
            if not validator.validate_null_mismatches(table_name, columns):
                validation_failures += 1
            if not validator.validate_datatype_mismatches(table_name, table_dict):
                validation_failures += 1
            
            if pk_column:
                if not validator.validate_checksums(table_name, pk_column, columns):
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
