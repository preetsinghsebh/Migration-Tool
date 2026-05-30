import logging

logger = logging.getLogger(__name__)

# A predefined set of common PostgreSQL datatypes for validation.
POSTGRES_COMMON_TYPES = {
    "SMALLINT", "INTEGER", "BIGINT", "DECIMAL", "NUMERIC", "REAL", "DOUBLE PRECISION",
    "SERIAL", "BIGSERIAL", "VARCHAR", "CHAR", "TEXT", "BYTEA", 
    "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "DATE", "TIME", "TIME WITH TIME ZONE",
    "INTERVAL", "BOOLEAN", "ENUM", "UUID", "JSON", "JSONB"
}

def is_valid_postgres_type(pg_type):
    """
    Validates if the generated PostgreSQL type string is structurally sound
    and within standard types.
    """
    if not pg_type:
        return False
        
    base_type = pg_type.split("(")[0].strip().upper()
    
    if base_type not in POSTGRES_COMMON_TYPES:
        logger.warning(f"Validation Warning: '{pg_type}' is not in the list of common PostgreSQL types.")
        return False
        
    return True
