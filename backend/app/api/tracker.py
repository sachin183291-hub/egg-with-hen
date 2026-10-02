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
    possible_paths = [
        os.path.join(base_dir, "backend", "best.pt"),
        os.path.join(base_dir, "backend", "yolov8s-world.pt"),
        os.path.join(base_dir, "backend", "yolov8s-worldv2.pt"),
        os.path.join(base_dir, "yolov8s-world.pt"),
        os.path.join(base_dir, "weights", "best.pt"),
        os.path.join(base_dir, "backend", "weights", "best.pt"),
        os.path.join(base_dir, "backend", "yolov8n.pt"),
        os.path.join(base_dir, "yolov8n.pt"),
        "best.pt",
    ]
    for p in possible_paths:
        if os.path.exists(p):
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

