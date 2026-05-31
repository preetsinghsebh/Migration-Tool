import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from connectors.postgres import PostgresConnector

def view_data(table_name="DATA_ORACLE"):
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    dbname = os.getenv("PG_DB", "target_db")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "secret")
    
    print(f"Connecting to PostgreSQL... (Host: {host}:{port}, DB: {dbname}, User: {user})")
    
    connector = PostgresConnector(host, port, dbname, user, password)
    try:
        connector.initialize_pool()
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")
        return
        
    with connector.get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                # Query the first 10 rows
                cursor.execute(f'SELECT * FROM "{table_name.upper()}" LIMIT 10')
                
                # Fetch headers
                headers = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                
                if not rows:
                    print(f"Table '{table_name.upper()}' is empty in PostgreSQL.")
                    connector.close_pool()
                    return
                    
                # Format headers and rows as a beautiful text table
                col_widths = [max(len(h), max(len(str(row[i])) for row in rows)) for i, h in enumerate(headers)]
                
                header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
                separator = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
                
                print("\n" + "=" * len(header_line))
                print(f"PostgreSQL Table: '{table_name.upper()}' (First 10 rows)")
                print("=" * len(header_line))
                print(header_line)
                print(separator)
                for row in rows:
                    print(" | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)))
                print("=" * len(header_line) + "\n")
                
            except Exception as e:
                print(f"Error querying table '{table_name.upper()}' in PostgreSQL: {e}")
                
    connector.close_pool()

if __name__ == "__main__":
    target = "DATA_ORACLE"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    view_data(target)
