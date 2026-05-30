import sys
import asyncio
import logging
import threading
import queue
import time
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
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

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
