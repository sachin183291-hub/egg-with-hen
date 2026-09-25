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
#   1. Trained custom model (egg_detector.pt = copy of user's best(3).pt)
#   2. Fallback to generic yolov8n.pt (ultralytics auto-downloads)

_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
_CUSTOM_MODEL = os.path.join(_THIS_DIR, "models", "egg_detector.pt")
_FALLBACK_MODEL = "yolov8n.pt"


def get_model_path() -> str:
    """
    Return the absolute path to the trained YOLO model.
    Uses egg_detector.pt (= user's trained best(3).pt) when present,
    otherwise falls back to yolov8n.pt.
    """
    if os.path.exists(_CUSTOM_MODEL):
        return _CUSTOM_MODEL
    print(f"[WARNING] Custom model not found at {_CUSTOM_MODEL}. Using yolov8n fallback.")
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
    from app.ai.stable_tracker import StableHenTracker

    model_path = get_model_path()
    tracker = StableHenTracker(model_path=model_path)
    return tracker.process_video(video_path, progress_callback=progress_callback)
