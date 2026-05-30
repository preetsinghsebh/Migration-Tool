import json
import logging
import os

from validators.type_validator import is_valid_postgres_type

logger = logging.getLogger(__name__)

class DatatypeConverter:
    """
    Converts Oracle datatypes to PostgreSQL compatible datatypes.
    Uses a configurable JSON mapping file.
    """
    def __init__(self, config_path=None):
        if not config_path:
            # Default to the config in the project directory
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'type_mappings.json')
            
        self.config_path = os.path.abspath(config_path)
        self.mappings = {}
        self.fallback = "TEXT"
        self._load_config()

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                self.mappings = config_data.get("mappings", {})
                self.fallback = config_data.get("fallback", "TEXT")
                
            # Normalize mappings to uppercase
            self.mappings = {k.upper(): v.upper() for k, v in self.mappings.items()}
            logger.info("Datatype mappings loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load type mappings from {self.config_path}: {e}")
            raise

    def convert_type(self, oracle_type, precision=None, scale=None):
        """
        Converts an Oracle type to a PostgreSQL type, taking into account precision and scale.
        Emits warnings for risky conversions.
        """
        if not oracle_type:
            logger.critical("No Oracle type provided for conversion. Using fallback.")
            return self.fallback

        base_oracle_type = oracle_type.upper().split("(")[0].strip()
        
        # Determine the mapped Postgres base type
        pg_base_type = self.mappings.get(base_oracle_type)
        
        if not pg_base_type:
            logger.warning(f"Risky Conversion: Unknown Oracle type '{base_oracle_type}'. Falling back to {self.fallback}.")
            pg_type = self.fallback
            return pg_type

        # Check for specific risky conversions
        self._check_risky_conversions(base_oracle_type, pg_base_type, precision, scale)

        # Apply precision and scale rules
        pg_type = self._apply_precision_scale(base_oracle_type, pg_base_type, precision, scale)

        # Validate the resulting type
        is_valid_postgres_type(pg_type)

        return pg_type

    def _check_risky_conversions(self, oracle_type, pg_type, precision, scale):
        """Generates warnings for known risky data type mappings."""
        if oracle_type == "DATE" and "TIMESTAMP" in pg_type:
            logger.warning("Risky Conversion: Oracle 'DATE' includes time. Mapping to Postgres 'TIMESTAMP'. Verify application behavior.")
            
        if oracle_type == "NUMBER" and precision is None:
            logger.warning("Risky Conversion: Oracle 'NUMBER' without precision mapped to NUMERIC. This defaults to max precision and may impact performance in Postgres.")

        if oracle_type in ["CLOB", "BLOB", "NCLOB"]:
            logger.info(f"Large Object detected: {oracle_type}. Mapped to {pg_type}. Ensure target database is configured for large data.")

    def _apply_precision_scale(self, oracle_type, pg_type, precision, scale):
        """Applies precision and scale to the mapped type where appropriate."""
        if oracle_type == "NUMBER":
            if scale == 0:
                if precision:
                    if precision <= 4:
                        return "SMALLINT"
                    elif precision <= 9:
                        return "INTEGER"
                    elif precision <= 18:
                        return "BIGINT"
                else:
                    return "NUMERIC" # NUMBER(38,0) or unknown precision
                    
            if precision is not None and scale is not None:
                return f"NUMERIC({precision}, {scale})"
            elif precision is not None:
                return f"NUMERIC({precision})"
            else:
                return "NUMERIC"

        elif oracle_type in ["VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR"]:
            if precision:
                return f"VARCHAR({precision})" if "VARCHAR" in pg_type else f"CHAR({precision})"
            
        return pg_type
