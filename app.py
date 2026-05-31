import sys
import asyncio
import logging
import threading
import queue
import time
import io
import csv
import os
from fastapi import FastAPI, BackgroundTasks, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn

import main as orchestrator

app = FastAPI(title="Oracle to PostgreSQL Migration Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log_queue = queue.Queue()

class QueueHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            self.handleError(record)

# Setup queue logging
q_handler = QueueHandler()
q_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(q_handler)
logging.getLogger().setLevel(logging.INFO)

app.mount("/static", StaticFiles(directory="static"), name="static")

migration_running = False

def run_migration_in_thread():
    global migration_running
    migration_running = True
    try:
        sys.argv = ["main.py", "--output-dir", "output", "--batch-size", "10000"]
        orchestrator.main()
    except Exception as e:
        logging.error(f"Migration crashed: {e}")
    finally:
        migration_running = False
        log_queue.put("DONE")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/start")
async def start_migration(background_tasks: BackgroundTasks):
    global migration_running
    if migration_running:
        return {"status": "error", "message": "Migration is already running."}
    
    while not log_queue.empty():
        log_queue.get()
        
    background_tasks.add_task(run_migration_in_thread)
    return {"status": "success", "message": "Migration started!"}

@app.get("/api/logs")
async def stream_logs(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = log_queue.get_nowait()
                if msg == "DONE":
                    yield {"data": "[COMPLETED] Migration pipeline finished."}
                    break
                yield {"data": msg}
            except queue.Empty:
                await asyncio.sleep(0.1)
    return EventSourceResponse(event_generator())

@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...), table_name: str = Form(...)):
    if not file.filename.lower().endswith('.csv'):
        return JSONResponse(status_code=400, content={"status": "error", "message": "Only CSV files are allowed."})
    
    try:
        contents = await file.read()
        decoded = contents.decode('utf-8-sig')
        csv_reader = csv.reader(io.StringIO(decoded))
        
        headers = [h.strip().upper() for h in next(csv_reader)]
        rows = [row for row in csv_reader if any(row)]
        
        if not headers:
            return JSONResponse(status_code=400, content={"status": "error", "message": "CSV file has no headers."})
            
        t_name = table_name.strip().upper()
        if not t_name:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Table name cannot be empty."})
            
        import re
        if not re.match(r'^[A-Z][A-Z0-9_]*$', t_name):
            return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid table name. Must start with a letter and contain only letters, numbers, and underscores."})
            
        oracle_user = os.getenv("ORACLE_USER", "system")
        oracle_pass = os.getenv("ORACLE_PASSWORD", os.getenv("ORACLE_PASS", "password"))
        oracle_dsn = os.getenv("ORACLE_DSN", "localhost:1521/FREEPDB1")
        
        from connectors.oracle import OracleConnector
        oracle_connector = OracleConnector(oracle_user, oracle_pass, oracle_dsn)
        oracle_connector.initialize_pool()
        
        with oracle_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :1", [t_name])
                table_exists = cursor.fetchone()[0] > 0
                
                if not table_exists:
                    col_defs = ", ".join([f'"{col}" VARCHAR2(255)' for col in headers])
                    create_sql = f'CREATE TABLE "{t_name}" ({col_defs})'
                    cursor.execute(create_sql)
                    logging.info(f"Created Oracle table '{t_name}' via frontend upload.")
                else:
                    cursor.execute(f'DROP TABLE "{t_name}" CASCADE CONSTRAINTS')
                    col_defs = ", ".join([f'"{col}" VARCHAR2(255)' for col in headers])
                    create_sql = f'CREATE TABLE "{t_name}" ({col_defs})'
                    cursor.execute(create_sql)
                    logging.info(f"Recreated Oracle table '{t_name}' to match CSV headers.")
                
                col_names_str = ", ".join([f'"{h}"' for h in headers])
                bind_placeholders = ", ".join([f":{i+1}" for i in range(len(headers))])
                insert_sql = f'INSERT INTO "{t_name}" ({col_names_str}) VALUES ({bind_placeholders})'
                
                cursor.executemany(insert_sql, rows)
                conn.commit()
                logging.info(f"Uploaded and loaded {len(rows)} rows into Oracle table '{t_name}' from CSV.")
                
        oracle_connector.close_pool()
        log_queue.put(f"[UPLOAD] Loaded CSV data successfully into Oracle table '{t_name}' ({len(rows)} rows).")
        
        return {"status": "success", "message": f"Successfully loaded {len(rows)} rows into Oracle table '{t_name}'!"}
        
    except Exception as e:
        logging.error(f"Error handling CSV upload: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Failed to load CSV: {str(e)}"})

@app.get("/api/download/{table_name}")
async def download_postgres_csv(table_name: str):
    t_name = table_name.strip().upper()
    if not t_name:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Table name cannot be empty."})
        
    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_dbname = os.getenv("PG_DB", "target_db")
    pg_user = os.getenv("PG_USER", "postgres")
    pg_pass = os.getenv("PG_PASSWORD", "secret")
    
    from connectors.postgres import PostgresConnector
    pg_connector = PostgresConnector(pg_host, pg_port, pg_dbname, pg_user, pg_pass)
    try:
        pg_connector.initialize_pool()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Failed to connect to PostgreSQL: {str(e)}"})
        
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        with pg_connector.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s",
                    [t_name]
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE LOWER(table_name) = LOWER(%s)",
                        [t_name]
                    )
                    if cursor.fetchone()[0] == 0:
                        pg_connector.close_pool()
                        return JSONResponse(status_code=404, content={"status": "error", "message": f"Table '{t_name}' does not exist in PostgreSQL."})

                cursor.execute(f'SELECT * FROM "{t_name}"')
                headers = [col[0] for col in cursor.description]
                writer.writerow(headers)
                
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    writer.writerows(rows)
                    
        pg_connector.close_pool()
        
        output.seek(0)
        headers_resp = {
            'Content-Disposition': f'attachment; filename="{t_name}_postgres.csv"',
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers_resp)
        
    except Exception as e:
        logging.error(f"Failed to export table {t_name}: {e}")
        try:
            pg_connector.close_pool()
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Export failed: {str(e)}"})

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
