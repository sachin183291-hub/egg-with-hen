"""
tracking.py — Public interface for the Stable Hen Tracking engine.

This module is the ONLY import that app.py / tracker.py needs.
All YOLO inference, ByteTrack, position matching, and permanent
hen-numbering logic stays inside stable_tracker.py.

Usage:
    from app.ai.tracking import process_video, get_model_path

    result = process_video(
        video_path="/tmp/upload_abc.mp4",
        progress_callback=my_callback,   # optional
    )
    # result = {"type": "completed", "total_hens": 42, ...}
"""

import os
from typing import Callable, Optional

# ─── Model path resolution ────────────────────────────────────────────────────
# Priority order:
#   1. User-trained best.pt in the project root/backend (the actual model used for
#      poultry hen-comb detection on uploaded videos)
#   2. Legacy egg_detector.pt path used by earlier experiments
#   3. Fallback to generic yolov8n.pt (ultralytics auto-downloads)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))

_MODEL_CANDIDATES = [
    os.path.join(_BACKEND_DIR, "best.pt"),
    os.path.join(_REPO_ROOT, "best.pt"),
    os.path.join(_REPO_ROOT, "backend", "best.pt"),
    os.path.join(_REPO_ROOT, "weights", "best.pt"),
    os.path.join(_BACKEND_DIR, "weights", "best.pt"),
    os.path.join(_THIS_DIR, "models", "egg_detector.pt"),
    os.path.join(_THIS_DIR, "models", "best.pt"),
    os.path.join(_THIS_DIR, "egg_detector.pt"),
    os.path.join(_BACKEND_DIR, "yolov8n.pt"),
    "best.pt",
]
_FALLBACK_MODEL = "yolov8n.pt"


def get_model_path() -> str:
    """
    Return the absolute path to the trained YOLO model.
    Prefer the project's actual best.pt before falling back to any generic model.
    """
    for candidate in _MODEL_CANDIDATES:
        if os.path.exists(candidate):
            return candidate

    print(
        f"[WARNING] No trained model was found in the project. "
        f"Checked: {', '.join(_MODEL_CANDIDATES)}. Using yolov8n fallback."
    )
    return _FALLBACK_MODEL


def process_video(
    video_path: str,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Run the stable hen tracking engine on a video file.

    Args:
        video_path:         Absolute path to the uploaded video file.
        progress_callback:  Optional callable that receives live update dicts:
                                {"type": "progress", "frame": N, ...}
                                {"type": "completed", "total_hens": N, ...}

    Returns:
        Final result dict:
            {
                "type": "completed",
                "total_hens": int,
                "frames_processed": int,
                "duration_seconds": float,
            }

    Raises:
        RuntimeError: if the video cannot be opened or model cannot be loaded.
    """
    from app.ai.fast_tracker import FastHenTracker

    model_path = get_model_path()
    tracker = FastHenTracker(model_path=model_path)
    return tracker.process_video(video_path, progress_callback=progress_callback)
