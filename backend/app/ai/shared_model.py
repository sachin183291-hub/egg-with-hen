"""
shared_model.py — Shared Singleton YOLO Model Manager for GioTag
Ensures only ONE instance of the YOLO model is ever loaded in memory,
keeping total container RAM well under the Render Free Tier 512MB limit.
"""
import os
import gc
import torch
import numpy as np

# Optimal threads for local multi-core PC (falls back to 2 on Render)
if os.environ.get("RENDER") == "true":
    torch.set_num_threads(2)
else:
    torch.set_num_threads(min(6, os.cpu_count() or 4))
try:
    torch.set_num_interop_threads(2)
except Exception:
    pass
torch.set_grad_enabled(False)

_SHARED_MODEL = None
_SHARED_MODEL_PATH = None

def resolve_model_path() -> str:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    is_cuda = torch.cuda.is_available()
    
    if is_cuda:
        candidates = [
            os.path.abspath(os.path.join(_this_dir, "../../best.pt")),
            os.path.abspath(os.path.join(_this_dir, "../../../best.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "best.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.pt")),
            "backend/best.pt",
            "best.pt",
            os.path.abspath(os.path.join(_this_dir, "../../best.onnx")),
            os.path.abspath(os.path.join(_this_dir, "../../../best.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "best.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.onnx")),
            "backend/best.onnx",
            "best.onnx",
        ]
    else:
        # On CPU: best.onnx is 11.4x faster (334ms vs 3800ms) with identical comb detection accuracy
        candidates = [
            os.path.abspath(os.path.join(_this_dir, "../../best.onnx")),
            os.path.abspath(os.path.join(_this_dir, "../../../best.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "best.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.onnx")),
            "backend/best.onnx",
            "best.onnx",
            os.path.abspath(os.path.join(_this_dir, "../../best.pt")),
            os.path.abspath(os.path.join(_this_dir, "../../../best.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "best.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.pt")),
            "backend/best.pt",
            "best.pt",
        ]
    
    candidates += [
        os.path.abspath(os.path.join(_this_dir, "models", "egg_detector.pt")),
        os.path.abspath(os.path.join(_this_dir, "../../yolov8n.pt")),
        os.path.abspath(os.path.join(os.getcwd(), "yolov8n.pt")),
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
    _SHARED_MODEL = YOLO(path_to_load, task="detect") if path_to_load.endswith(".onnx") else YOLO(path_to_load)
    _SHARED_MODEL_PATH = path_to_load

    # Warmup with exact inference resolution 352 to eliminate initial 3-second graph compilation lag
    try:
        _dummy = np.zeros((352, 352, 3), dtype=np.uint8)
        _SHARED_MODEL.predict(_dummy, imgsz=352, verbose=False)
        print("[AI-SHARED] Shared model initialized and warmed up successfully at imgsz=352.")
    except Exception as e:
        print(f"[AI-SHARED] Warmup note: {e}")

    gc.collect()
    return _SHARED_MODEL
