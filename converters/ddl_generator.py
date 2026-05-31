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
        
    def _map_default_value(self, oracle_default):
        if not oracle_default:
            return None
        val = oracle_default.upper().strip()
        if "NEXTVAL" in val:
            # Remove all quotes first to avoid parsing issues with embedded quotes
            clean = oracle_default.replace('"', '').replace("'", "").strip()
            # Remove .NEXTVAL suffix
            if clean.upper().endswith(".NEXTVAL"):
                clean = clean[:-8].strip()
            # Strip schema prefix if present
            if "." in clean:
                clean = clean.split(".")[-1].strip()
            return f"DEFAULT nextval('\"{clean}\"')"
        
        if val == "SYSDATE" or val == "CURRENT_DATE":
            return "DEFAULT CURRENT_TIMESTAMP"
        if val == "USER":
            return "DEFAULT CURRENT_USER"
            
        return f"DEFAULT {oracle_default}"

    def generate_ddl(self, schema_json_path, output_dir):
        """
        Reads schema JSON and generates PostgreSQL CREATE TABLE statements.
        Creates one .sql file per table in output_dir/tables/ directory.
        Creates sequences.sql and constraints.sql directly in output_dir.
        
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
            
        # Ensure the output directories exist
        os.makedirs(os.path.abspath(output_dir), exist_ok=True)
        tables_output_dir = os.path.join(output_dir, "tables")
        os.makedirs(tables_output_dir, exist_ok=True)
            
        # 1. Generate sequences DDL if sequences.json exists
        sequences_json_path = os.path.join(os.path.dirname(schema_json_path), "sequences.json")
        if os.path.exists(sequences_json_path):
            try:
                with open(sequences_json_path, 'r', encoding='utf-8') as sf:
                    sequences = json.load(sf)
                
                sequences_sql_path = os.path.join(output_dir, "sequences.sql")
                with open(sequences_sql_path, 'w', encoding='utf-8') as f:
                    f.write("-- Auto-generated PostgreSQL Sequences DDL\n\n")
                    for seq in sequences:
                        seq_name = seq["name"]
                        min_val = seq.get("min_value")
                        max_val = seq.get("max_value")
                        increment = seq.get("increment_by", 1)
                        cycle = seq.get("cycle", False)
                        cache = seq.get("cache_size", 0)
                        last_num = seq.get("last_number")
                        
                        PG_MAX_BIGINT = 9223372036854775807
                        
                        start_val = last_num if last_num is not None else (min_val if min_val is not None else 1)
                        if start_val > PG_MAX_BIGINT:
                            start_val = PG_MAX_BIGINT
                        
                        sql = f"CREATE SEQUENCE IF NOT EXISTS \"{seq_name}\"\n"
                        sql += f"    START WITH {start_val}\n"
                        sql += f"    INCREMENT BY {increment}\n"
                        if min_val is not None:
                            if min_val > PG_MAX_BIGINT:
                                min_val = PG_MAX_BIGINT
                            sql += f"    MINVALUE {min_val}\n"
                        if max_val is not None:
                            if max_val > PG_MAX_BIGINT:
                                max_val = PG_MAX_BIGINT
                            sql += f"    MAXVALUE {max_val}\n"
                        if cache > 1:
                            sql += f"    CACHE {cache}\n"
                        else:
                            sql += f"    CACHE 1\n"
                        sql += "    CYCLE;\n\n" if cycle else "    NO CYCLE;\n\n"
                        f.write(sql)
                logger.info(f"Generated sequences DDL in {sequences_sql_path}")
            except Exception as e:
                logger.warning(f"Failed to generate sequences DDL: {e}")

        # 2. Build constraint lookup map for FK resolution
        constraint_map = {}
        for table in tables:
            tname = table.get("table_name")
            constraints = table.get("constraints", [])
            for cons in constraints:
                ctype = cons.get("type")
                if ctype in ('P', 'U'):
                    cname = cons.get("name")
                    cols = cons.get("columns", [])
                    constraint_map[cname] = (tname, cols)

        count = 0
        all_fks = []
            
        for table in tables:
            table_name = table.get("table_name")
            columns = table.get("columns", [])
            constraints = table.get("constraints", [])
            
            if not table_name or not columns:
                continue
                
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
            
            output_sql_path = os.path.join(tables_output_dir, f"{table_name}.sql")
            
            with open(output_sql_path, 'w', encoding='utf-8') as f:
                f.write(f"-- Auto-generated PostgreSQL DDL for {table_name}\n\n")
                f.write(f"DROP TABLE IF EXISTS \"{table_name}\" CASCADE;\n\n")
                f.write(f"CREATE TABLE \"{table_name}\" (\n")
                
                col_defs = []
                for col in columns:
                    col_name = col.get("name")
                    oracle_type = col.get("datatype")
                    precision = col.get("precision")
                    scale = col.get("scale")
                    nullable = col.get("nullable", True)
                    
                    pg_type = self.converter.convert_type(oracle_type, precision, scale)
                    
                    col_def = f"    \"{col_name}\" {pg_type}"
                    
                    default_value = col.get("default_value")
                    mapped_default = self._map_default_value(default_value)
                    if mapped_default:
                        col_def += f" {mapped_default}"
                        
                    if not nullable:
                        col_def += " NOT NULL"
                    col_defs.append(col_def)
                
                # Append PK/UQ Constraints inside CREATE TABLE
                for pk in pk_constraints:
                    cols_str = ", ".join(f'"{c}"' for c in pk["columns"])
                    col_defs.append(f"    CONSTRAINT \"{pk['name']}\" PRIMARY KEY ({cols_str})")
                    
                for uq in uq_constraints:
                    cols_str = ", ".join(f'"{c}"' for c in uq["columns"])
                    col_defs.append(f"    CONSTRAINT \"{uq['name']}\" UNIQUE ({cols_str})")
                    
                f.write(",\n".join(col_defs))
                f.write("\n);\n\n")
                
                # Resolve Foreign Key constraints and save them to be written to constraints.sql
                for fk in fk_constraints:
                    cols_str = ", ".join(f'"{c}"' for c in fk["columns"])
                    ref_constraint = fk.get("r_constraint_name")
                    if ref_constraint and ref_constraint in constraint_map:
                        ref_table, ref_cols = constraint_map[ref_constraint]
                        ref_cols_str = ", ".join(f'"{c}"' for c in ref_cols)
                        fk_sql = (
                            f"ALTER TABLE \"{table_name}\"\n"
                            f"    ADD CONSTRAINT \"{fk['name']}\" FOREIGN KEY ({cols_str})\n"
                            f"    REFERENCES \"{ref_table}\" ({ref_cols_str});\n\n"
                        )
                    else:
                        fk_sql = (
                            f"ALTER TABLE \"{table_name}\"\n"
                            f"    ADD CONSTRAINT \"{fk['name']}\" FOREIGN KEY ({cols_str})\n"
                            f"    REFERENCES /* TODO: resolve {fk['r_constraint_name']} */;\n\n"
                        )
                    all_fks.append(fk_sql)
            
            count += 1
                
        # Write consolidated constraints file
        constraints_sql_path = os.path.join(output_dir, "constraints.sql")
        if all_fks:
            with open(constraints_sql_path, 'w', encoding='utf-8') as f:
                f.write("-- Auto-generated PostgreSQL Foreign Keys DDL\n\n")
                f.write("".join(all_fks))
            logger.info(f"Generated consolidated constraints DDL in {constraints_sql_path}")
            
        logger.info(f"DDL generation completed. Generated {count} table DDL files in {tables_output_dir}.")
        return count
