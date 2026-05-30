import json
import logging
import os
from converters.datatype_converter import DatatypeConverter

logger = logging.getLogger(__name__)

class DDLGenerator:
    """
    Generates PostgreSQL CREATE TABLE statements from an extracted JSON schema.
    """
    def __init__(self, converter=None):
        self.converter = converter if converter else DatatypeConverter()
        
    def generate_ddl(self, schema_json_path, output_dir):
        """
        Reads schema JSON and generates PostgreSQL CREATE TABLE statements.
        Creates one .sql file per table in the specified output directory.
        
        Args:
            schema_json_path (str): Path to the input JSON schema.
            output_dir (str): Path to the directory where .sql files will be saved.
            
        Returns:
            int: Number of tables generated.
        """
        logger.info(f"Starting DDL generation from {schema_json_path} to {output_dir}/")
        
        try:
            with open(schema_json_path, 'r', encoding='utf-8') as f:
                tables = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read schema JSON: {e}")
            raise
            
        # Ensure the output directory exists
        os.makedirs(os.path.abspath(output_dir), exist_ok=True)
            
        count = 0
            
        for table in tables:
            table_name = table.get("table_name")
            columns = table.get("columns", [])
            constraints = table.get("constraints", [])
            
            if not table_name or not columns:
                continue
                
            # Separate constraints
            pk_constraints = []
            uq_constraints = []
            fk_constraints = []
            
            for cons in constraints:
                ctype = cons.get("type")
                if ctype == 'P':
                    pk_constraints.append(cons)
                elif ctype == 'U':
                    uq_constraints.append(cons)
                elif ctype == 'R':
                    fk_constraints.append(cons)
            
            output_sql_path = os.path.join(output_dir, f"{table_name}.sql")
            
            with open(output_sql_path, 'w', encoding='utf-8') as f:
                f.write(f"-- Auto-generated PostgreSQL DDL for {table_name}\n\n")
                f.write(f"CREATE TABLE {table_name} (\n")
                
                col_defs = []
                for col in columns:
                    col_name = col.get("name")
                    oracle_type = col.get("datatype")
                    precision = col.get("precision")
                    scale = col.get("scale")
                    nullable = col.get("nullable", True)
                    
                    # Convert to PostgreSQL type
                    pg_type = self.converter.convert_type(oracle_type, precision, scale)
                    
                    col_def = f"    {col_name} {pg_type}"
                    if not nullable:
                        col_def += " NOT NULL"
                    col_defs.append(col_def)
                
                # Append PK/UQ Constraints inside CREATE TABLE
                for pk in pk_constraints:
                    cols_str = ", ".join(pk["columns"])
                    col_defs.append(f"    CONSTRAINT {pk['name']} PRIMARY KEY ({cols_str})")
                    
                for uq in uq_constraints:
                    cols_str = ", ".join(uq["columns"])
                    col_defs.append(f"    CONSTRAINT {uq['name']} UNIQUE ({cols_str})")
                    
                f.write(",\n".join(col_defs))
                f.write("\n);\n\n")
                
                # Append FK Constraints as ALTER TABLE
                for fk in fk_constraints:
                    cols_str = ", ".join(fk["columns"])
                    # Note: full FK mapping requires knowing the referenced table's columns.
                    # Oracle extracts 'r_constraint_name', but to map properly to Postgres,
                    # we often just write the skeleton or need cross-reference.
                    # We'll emit a warning or simplified ALTER TABLE.
                    f.write(f"ALTER TABLE {table_name}\n")
                    f.write(f"    ADD CONSTRAINT {fk['name']} FOREIGN KEY ({cols_str})\n")
                    f.write(f"    REFERENCES /* TODO: resolve {fk['r_constraint_name']} */;\n\n")
            
            count += 1
                
        logger.info(f"DDL generation completed. Generated {count} files in {output_dir}.")
        return count
