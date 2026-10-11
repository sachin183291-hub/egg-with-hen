"""
shared_model.py — Shared Singleton YOLO Model Manager for GioTag
Ensures only ONE instance of the YOLO model is ever loaded in memory,
keeping total container RAM well under the Render Free Tier 512MB limit.
"""
import os
import gc
import torch
import numpy as np

# Restrict thread pools to 1 thread to eliminate multi-thread memory multiplication
torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except Exception:
    pass
torch.set_grad_enabled(False)

_SHARED_MODEL = None
_SHARED_MODEL_PATH = None

def resolve_model_path() -> str:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(_this_dir, "../../best.pt")),
        os.path.abspath(os.path.join(_this_dir, "../../../best.pt")),
        os.path.abspath(os.path.join(os.getcwd(), "best.pt")),
        os.path.abspath(os.path.join(os.getcwd(), "backend", "best.pt")),
        os.path.abspath(os.path.join(_this_dir, "models", "egg_detector.pt")),
        os.path.abspath(os.path.join(_this_dir, "../../yolov8n.pt")),
        os.path.abspath(os.path.join(os.getcwd(), "yolov8n.pt")),
        "best.pt",
        "yolov8n.pt",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return "yolov8n.pt"

def get_shared_model(model_path: str = None):
    """
    Returns the single global in-memory instance of the YOLO model.
    Subsequent calls return the already-loaded instance immediately without allocating RAM.
    """
    global _SHARED_MODEL, _SHARED_MODEL_PATH
    if _SHARED_MODEL is not None:
        return _SHARED_MODEL

    from ultralytics import YOLO

    path_to_load = model_path if (model_path and os.path.exists(model_path)) else resolve_model_path()
    print(f"[AI-SHARED] Loading single shared YOLO instance from: {path_to_load}")
    _SHARED_MODEL = YOLO(path_to_load)
    _SHARED_MODEL_PATH = path_to_load

    # Light warmup with 320x320 to avoid large tensor allocation
    try:
        _dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        _SHARED_MODEL.predict(_dummy, imgsz=320, verbose=False)
        print("[AI-SHARED] Shared model initialized and warmed up successfully.")
    except Exception as e:
        print(f"[AI-SHARED] Warmup note: {e}")

    gc.collect()
    return _SHARED_MODEL
