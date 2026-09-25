import os
import uuid
import threading
import queue
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
import tempfile

from app.ai.stable_tracker import StableHenTracker

router = APIRouter(prefix="/api/tracker", tags=["Hen Tracking"])

TRACKING_JOBS = {}


import numpy as np
import cv2
import base64

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


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload video → get job_id. WebSocket will start streaming annotated frames."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    model_path = get_model_path()
    if not os.path.exists(model_path):
        raise HTTPException(status_code=500, detail="Model file best.pt not found.")

    temp_dir = None
    if os.path.exists("D:\\"):
        temp_dir = "D:\\giotag_temp"
        os.makedirs(temp_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] or ".mp4"
    fd, input_path = tempfile.mkstemp(suffix=ext, prefix="track_in_", dir=temp_dir)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        if os.path.exists(input_path):
            os.remove(input_path)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    job_id = str(uuid.uuid4())
    TRACKING_JOBS[job_id] = {
        "status": "ready",
        "video_path": input_path,
        "model_path": model_path,
        "visible_hens": 0,
        "total_hens": 0,
        "progress": 0,
    }
    return {"job_id": job_id, "status": "ready"}


@router.websocket("/ws_stream/{job_id}")
async def ws_stream_tracking_video(websocket: WebSocket, job_id: str):
    await websocket.accept()

    job = TRACKING_JOBS.get(job_id)
    if not job:
        await websocket.close(code=1008, reason="Job not found")
        return

    video_path = job.get("video_path")
    model_path = job.get("model_path")

    if not video_path or not os.path.exists(video_path):
        await websocket.close(code=1008, reason="Video file not found")
        return
    if not os.path.exists(model_path):
        await websocket.close(code=1011, reason="Model not found")
        return

    job["status"] = "processing"

    frame_queue: queue.Queue = queue.Queue()
    tracker = StableHenTracker(model_path=model_path)

    def producer():
        try:
            tracker.process_to_queue(video_path, frame_queue, job)
        except Exception as e:
            print(f"[Tracker] Producer error: {e}")
            import traceback; traceback.print_exc()
            frame_queue.put(None)

    t = threading.Thread(target=producer, daemon=True)
    t.start()

    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: frame_queue.get(timeout=30)),
                    timeout=35,
                )
            except (asyncio.TimeoutError, Exception):
                break

            if item is None:
                break

            await websocket.send_json(item)

            await asyncio.sleep(0)

        # Send final total hens and completion state
        final_total = job.get("total_hens", 0)
        try:
            await websocket.send_json({
                "done": True,
                "progress": 100,
                "visible_hens": 0,
                "total_hens": final_total,
            })
            await asyncio.sleep(0.05)
        except Exception:
            pass

        await websocket.close(code=1000)
        job["status"] = "done"

    except WebSocketDisconnect:
        print(f"[Tracker] Client disconnected from {job_id}")
    except Exception as e:
        print(f"[Tracker] WS error: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception:
            pass


@router.get("/progress/{job_id}")
async def get_progress(job_id: str):
    job = TRACKING_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status":       job.get("status"),
        "progress":     job.get("progress", 0),
        "total_hens":   job.get("total_hens", 0),
    }

@router.websocket("/ws_live")
async def ws_live_tracking(websocket: WebSocket):
    await websocket.accept()
    model_path = get_model_path()
    if not os.path.exists(model_path):
        await websocket.close(code=1011, reason="Model not found")
        return

    tracker = StableHenTracker(model_path=model_path)
    frame_no = 0

    try:
        while True:
            # Receive base64 image or json from client
            data = await websocket.receive_text()
            if data.startswith("data:image"):
                data = data.split(",")[1]
            
            img_data = base64.b64decode(data)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            frame_no += 1
            b64, vis_count, tot_count = tracker.process_frame(frame, frame_no, fps=5.0)

            await websocket.send_json({
                "frame": b64,
                "visible_hens": vis_count,
                "total_hens": tot_count
            })
            await asyncio.sleep(0)

    except WebSocketDisconnect:
        print("[Tracker] Live client disconnected")
    except Exception as e:
        print(f"[Tracker] Live WS error: {e}")
        try:
            await websocket.close(code=1011)
        except:
            pass
