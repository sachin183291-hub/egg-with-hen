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
        "backend/best.pt",
        "best.pt",
        os.path.join(backend_dir, "best.onnx"),
        os.path.join(base_dir, "best.onnx"),
        os.path.join(base_dir, "backend", "best.onnx"),
        os.path.abspath(os.path.join(os.getcwd(), "best.onnx")),
        os.path.abspath(os.path.join(os.getcwd(), "backend", "best.onnx")),
        "backend/best.onnx",
        "best.onnx",
        os.path.join(backend_dir, "yolov8n.pt"),
        os.path.join(base_dir, "yolov8n.pt"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            print(f"[TRACKER] Found model at: {p}")
            return p
    return "yolov8n.pt"

@router.post("/live_frame")
def live_frame(
    frame: UploadFile = File(...),
    frame_number: int = Form(0),
    video_time: float = Form(0.0)
):
    global global_live_tracker
    if global_live_tracker is None:
        model_path = get_model_path()
        global_live_tracker = OpticalHenTracker(model_path)
        
    raw = frame.file.read()
    np_arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    if img is None:
        return {"success": False, "error": "Cannot decode frame"}
        
    result = global_live_tracker.process_live_frame(img, frame_number, video_time)
    return result

@router.post("/reset")
def reset_tracking():
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
UPLOAD_DIR = (PROJECT_ROOT / "uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload")
async def tracker_upload(file: UploadFile = File(...)):
    try:
        raw_name = file.filename or "video.mp4"
        safe_filename = Path(raw_name).name
        temp_path = UPLOAD_DIR / safe_filename
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Return immediately so upload finishes in milliseconds without CPU bottleneck
        return {"success": True, "filename": safe_filename}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/start_stream")
async def tracker_start_stream(source: StreamSource):
    if flask_app:
        flask_app.active_stream = source.video_source
    return {"success": True}

@router.post("/stop_stream")
async def tracker_stop_stream():
    if flask_app:
        flask_app.active_stream = None
        flask_app.current_total_count = 0
        flask_app.current_live_count = 0
    return {"success": True}

@router.get("/stream_count")
async def tracker_stream_count():
    count = 0
    live = 0
    if flask_app:
        count = getattr(flask_app, 'current_total_count', 0)
        live = getattr(flask_app, 'current_live_count', 0)
    return {"success": True, "count": count, "live_count": live}

@router.get("/stream_video/{filename:path}")
def stream_video_file(filename: str):
    import urllib.parse
    clean_filename = urllib.parse.unquote(filename)
    filepath = str(UPLOAD_DIR / clean_filename)
    if not os.path.exists(filepath):
        # Fallback check relative to cwd or root uploads
        possible = [
            os.path.abspath(os.path.join("uploads", filename)),
            os.path.abspath(os.path.join("backend", "uploads", filename)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../uploads", filename)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../demo_hen_video.mp4")),
            os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
        ]
        found = next((p for p in possible if os.path.exists(p)), None)
        if found:
            filepath = found
        else:
            raise HTTPException(status_code=404, detail=f"Video '{filename}' not found on server")

    opt_file = UPLOAD_DIR / f"_opt_{clean_filename}"
    if opt_file.exists():
        filepath = str(opt_file)

    if not flask_app:
        raise HTTPException(status_code=500, detail="Video streaming module not available")
        
    ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
    stream_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, no-transform",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    }
    return StreamingResponse(
        flask_app._sync_generate_frames(filepath, ref),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers=stream_headers
    )

@router.get("/stream_video")
def stream_video_cam():
    if not flask_app:
        raise HTTPException(status_code=500, detail="Streaming module not initialized")
    
    stream_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, no-transform",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    }
    
    # In cloud environments without physical camera, stream demo hen video
    if os.environ.get("RENDER") == "true":
        demo_paths = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../demo_hen_video.mp4")),
            os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
        ]
        demo_found = next((p for p in demo_paths if os.path.exists(p)), None)
        if demo_found:
            ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
            return StreamingResponse(
                flask_app._sync_generate_frames(demo_found, ref),
                media_type='multipart/x-mixed-replace; boundary=frame',
                headers=stream_headers
            )
        raise HTTPException(status_code=400, detail="Server camera not available in cloud deployment. Please use video upload.")
        
    ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
    return StreamingResponse(
        flask_app._sync_generate_frames('camera', ref),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers=stream_headers
    )
