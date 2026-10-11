import os
import uuid
import threading
import queue
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
import tempfile

from app.ai.optical_tracker import OpticalHenTracker

router = APIRouter(prefix="/api/tracker", tags=["Hen Tracking"])

TRACKING_JOBS = {}
global_live_tracker = None


import numpy as np
import cv2
import base64
import json

def get_model_path():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    possible_paths = [
        os.path.join(backend_dir, "best.pt"),
        os.path.join(base_dir, "best.pt"),
        os.path.join(base_dir, "backend", "best.pt"),
        os.path.abspath(os.path.join(os.getcwd(), "best.pt")),
        os.path.abspath(os.path.join(os.getcwd(), "backend", "best.pt")),
        os.path.join(backend_dir, "weights", "best.pt"),
        os.path.join(base_dir, "weights", "best.pt"),
        os.path.join(backend_dir, "yolov8n.pt"),
        os.path.join(base_dir, "yolov8n.pt"),
        "best.pt",
    ]
    for p in possible_paths:
        if os.path.exists(p):
            print(f"[TRACKER] Found model at: {p}")
            return p
    return "yolov8n.pt"

@router.post("/live_frame")
async def live_frame(
    frame: UploadFile = File(...),
    frame_number: int = Form(0),
    video_time: float = Form(0.0)
):
    global global_live_tracker
    if global_live_tracker is None:
        model_path = get_model_path()
        global_live_tracker = OpticalHenTracker(model_path)
        
    raw = await frame.read()
    np_arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    if img is None:
        return {"success": False, "error": "Cannot decode frame"}
        
    result = global_live_tracker.process_live_frame(img, frame_number, video_time)
    return result

@router.post("/reset")
async def reset_tracking():
    global global_live_tracker
    if global_live_tracker is not None:
        global_live_tracker.reset_state()
    return {"success": True}

# ─── Flask Legacy Integration for Hen Comb Tracking ────────────────────────────
import sys
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if base_dir not in sys.path:
    sys.path.append(base_dir)

try:
    import flask_app
    print("[TRACKER] flask_app loaded successfully for stream processing.")
except Exception as e:
    print(f"[TRACKER] Notice: Could not import flask_app: {e}")
    flask_app = None

class StreamSource(BaseModel):
    video_source: str = "camera"

import shutil

UPLOAD_DIR = Path("uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload")
async def tracker_upload(file: UploadFile = File(...)):
    filename = file.filename
    temp_path = UPLOAD_DIR / filename
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"success": True, "filename": filename}

@router.post("/start_stream")
async def tracker_start_stream(source: StreamSource):
    if flask_app:
        flask_app.active_stream = source.video_source
    return {"success": True}

@router.post("/stop_stream")
async def tracker_stop_stream():
    if flask_app:
        flask_app.active_stream = None
    return {"success": True}

@router.get("/stream_count")
async def tracker_stream_count():
    count = 0
    if flask_app and hasattr(flask_app, 'current_total_count'):
        count = flask_app.current_total_count
    return {"success": True, "count": count}

@router.get("/stream_video/{filename}")
async def stream_video_file(filename: str):
    filepath = str(UPLOAD_DIR / filename)
    if not os.path.exists(filepath):
        # Fallback check relative to cwd
        alt_path = os.path.abspath(os.path.join("uploads", filename))
        if os.path.exists(alt_path):
            filepath = alt_path
        else:
            raise HTTPException(status_code=404, detail=f"Video '{filename}' not found on server")
    if not flask_app:
        raise HTTPException(status_code=500, detail="Video streaming module not available")
    ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
    return StreamingResponse(
        flask_app._sync_generate_frames(filepath, ref),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )

@router.get("/stream_video")
async def stream_video_cam():
    if not flask_app:
        raise HTTPException(status_code=500, detail="Streaming module not initialized")
    if os.environ.get("RENDER") == "true":
        raise HTTPException(status_code=400, detail="Server camera not available in cloud deployment. Please use video upload or client camera.")
    ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
    return StreamingResponse(
        flask_app._sync_generate_frames('camera', ref),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )
