import os
import uuid
import time
import asyncio
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import tracking engine from the existing app structure
from app.ai.tracking import process_video

# ─── FastAPI Application ──────────────────────────────────────────────────────
app = FastAPI(title="GioTag Tracker Backend")

# ─── CORS Configuration ───────────────────────────────────────────────────────
# Allow frontend to communicate with backend
origins = [
    "http://localhost:5173", # Vite default
    "https://localhost:5173", # Vite basic-ssl
    "http://localhost:3000", # React default
    "https://localhost:3000",
    "http://127.0.0.1:5173",
    "https://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Data Structures ──────────────────────────────────────────────────────────
# Store final results and status for each job
job_store: Dict[str, Dict[str, Any]] = {}

# ─── WebSocket Manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_message(self, message: dict, job_id: str):
        if job_id in self.active_connections:
            try:
                await self.active_connections[job_id].send_json(message)
            except Exception:
                self.disconnect(job_id)

manager = ConnectionManager()

# ─── Background Processing Task ───────────────────────────────────────────────
def run_tracking_job(job_id: str, video_path: str, loop: asyncio.AbstractEventLoop, original_filename: str):
    last_update_time = 0.0

    def progress_callback(data: dict):
        nonlocal last_update_time
        current_time = time.time()
        
        # Throttle WebSocket live progress updates to ~4 times per second (0.25s)
        is_final = data.get("type") in ("completed", "error")
        if not is_final and (current_time - last_update_time < 0.25):
            return
            
        last_update_time = current_time
        data["job_id"] = job_id
        
        # Send via WebSocket using the main event loop
        asyncio.run_coroutine_threadsafe(manager.send_message(data, job_id), loop)

    try:
        start_time = time.time()
        # tracking.py handles YOLO inference, ByteTrack, positions, and live counting
        result = process_video(video_path, progress_callback=progress_callback)
        processing_time = time.time() - start_time
        
        # Save final result in memory (not storing video)
        total_hens = result.get("total_hens", 0)
        job_store[job_id] = {
            "job_id": job_id,
            "status": "completed",
            "original_filename": original_filename,
            "total_hens": total_hens,
            "processing_time": processing_time,
            "timestamp": time.time()
        }
        
        # Send final completion message via WebSocket
        final_msg = {
            "type": "completed",
            "job_id": job_id,
            "total_hens": total_hens,
            "status": "completed"
        }
        asyncio.run_coroutine_threadsafe(manager.send_message(final_msg, job_id), loop)

    except Exception as e:
        # Save error status
        job_store[job_id] = {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
            "timestamp": time.time()
        }
        
        # Send error message via WebSocket
        err_msg = {
            "type": "error",
            "job_id": job_id,
            "message": str(e)
        }
        asyncio.run_coroutine_threadsafe(manager.send_message(err_msg, job_id), loop)
    
    finally:
        # CLEANUP: Delete temporary video once processing is done
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except OSError as e:
                print(f"Failed to delete temp video {video_path}: {e}")


# ─── API Routes ───────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Accepts video file, creates a unique job_id, saves a temp file, 
    starts tracking.py engine in background, and returns immediately.
    """
    job_id = str(uuid.uuid4())
    
    job_store[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "original_filename": file.filename,
        "timestamp": time.time()
    }
    
    # Save temporary video for processing
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(exist_ok=True)
    temp_path = temp_dir / f"{job_id}_{file.filename}"
    
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())
        
    # Get main event loop to allow thread to use WebSockets safely
    loop = asyncio.get_running_loop()
    
    # Run processing without blocking the HTTP response
    background_tasks.add_task(
        run_tracking_job, 
        job_id=job_id, 
        video_path=str(temp_path), 
        loop=loop,
        original_filename=file.filename
    )
    
    return {
        "job_id": job_id,
        "status": "processing"
    }


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket connection for frontend to receive live progress updates.
    """
    await manager.connect(websocket, job_id)
    try:
        # Keep the connection open
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id)


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    """
    Returns the saved final result (final hen count + metadata).
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return job_store[job_id]


@app.get("/health")
async def health_check():
    """
    Simple health check for the tracker app.
    """
    return {"status": "ok"}
