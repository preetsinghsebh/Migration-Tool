import os
import sys
import csv
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from connectors.oracle import OracleConnector

def load_csv_to_oracle(csv_file_path, table_name):
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found at '{csv_file_path}'")
        return
        
    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASSWORD")
    dsn = os.getenv("ORACLE_DSN")
    
    print(f"Connecting to Oracle... (DSN: {dsn}, User: {user})")
    connector = OracleConnector(user, password, dsn)
    try:
        connector.initialize_pool()
    except Exception as e:
        print(f"Failed to connect to Oracle: {e}")
        return

    with connector.get_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Read CSV headers and rows
            with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                headers = [h.strip().upper() for h in next(reader)]
                rows = [row for row in reader if any(row)] # skip empty lines
                
            if not headers:
                print("Error: CSV file is empty or has no header row.")
                return
                
            print(f"Read {len(headers)} columns and {len(rows)} rows from CSV.")
            
            # 2. Check if table exists, if not, create it with VARCHAR2 columns
            cursor.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :1", [table_name.upper()])
            table_exists = cursor.fetchone()[0] > 0
            
            if not table_exists:
                print(f"Table '{table_name.upper()}' does not exist in Oracle. Creating it...")
                col_defs = ", ".join([f'"{col}" VARCHAR2(255)' for col in headers])
                create_sql = f'CREATE TABLE "{table_name.upper()}" ({col_defs})'
                try:
                    cursor.execute(create_sql)
                    print(f"Created table '{table_name.upper()}'.")
                except Exception as e:
                    print(f"Failed to create table: {e}")
                    connector.close_pool()
                    return
            else:
                print(f"Table '{table_name.upper()}' already exists. Recreating it...")
                try:
                    cursor.execute(f'DROP TABLE "{table_name.upper()}" CASCADE CONSTRAINTS')
                    col_defs = ", ".join([f'"{col}" VARCHAR2(255)' for col in headers])
                    create_sql = f'CREATE TABLE "{table_name.upper()}" ({col_defs})'
                    cursor.execute(create_sql)
                    print(f"Recreated table '{table_name.upper()}'.")
                except Exception as e:
                    print(f"Failed to recreate table: {e}")
                    connector.close_pool()
                    return

            # 3. Insert rows into Oracle
            col_names_str = ", ".join([f'"{h}"' for h in headers])
            bind_placeholders = ", ".join([f":{i+1}" for i in range(len(headers))])
            insert_sql = f'INSERT INTO "{table_name.upper()}" ({col_names_str}) VALUES ({bind_placeholders})'
            
            try:
                cursor.executemany(insert_sql, rows)
                conn.commit()
                print(f"Successfully loaded {len(rows)} rows into Oracle table '{table_name.upper()}'!")
            except Exception as e:
                print(f"Failed to insert data: {e}")
                conn.rollback()
                
    connector.close_pool()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python load_csv_to_oracle.py <path_to_csv_file> <target_table_name>")
        print("Example: python load_csv_to_oracle.py my_data.csv CUSTOMERS")
    else:
        csv_path = sys.argv[1]
        target_table = sys.argv[2]
        load_csv_to_oracle(csv_path, target_table)
