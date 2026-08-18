"""
AI Image Verification Pipeline — Error Level Analysis (ELA).
Detects potential image manipulation by analyzing compression artifacts.
Clearly labeled as AI-ASSISTED VERIFICATION (not ground truth).
Architecture supports plugging in a trained PyTorch model later.
"""
import io
import numpy as np
from typing import Dict, Any

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def perform_ela_analysis(image_bytes: bytes, quality: int = 90) -> Dict[str, Any]:
    """
    Error Level Analysis — re-saves image at fixed quality and measures pixel differences.
    Areas with higher ELA values may indicate tampering (added/edited content).

    Returns:
        ela_score: normalized score 0-1 (higher = more anomalous)
        suspicious_regions: count of high-ela pixel blobs
    """
    if not PIL_AVAILABLE:
        return {"ela_score": 0.0, "suspicious_regions": 0, "available": False}

    try:
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Re-save at controlled quality
        buffer = io.BytesIO()
        original.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")

        # Compute pixel-wise difference
        orig_arr = np.array(original, dtype=np.float32)
        recomp_arr = np.array(recompressed, dtype=np.float32)
        ela_arr = np.abs(orig_arr - recomp_arr)

        # Scale for visualization
        ela_max = ela_arr.max()
        if ela_max > 0:
            ela_normalized = ela_arr / ela_max
        else:
            ela_normalized = ela_arr

        ela_mean = float(ela_normalized.mean())
        ela_std = float(ela_normalized.std())

        # High ELA in concentrated regions suggests tampering
        # Count pixels significantly above mean
        threshold = ela_mean + 2 * ela_std
        high_ela_pixels = int(np.sum(ela_normalized > threshold))
        total_pixels = ela_normalized.shape[0] * ela_normalized.shape[1]
        suspicious_ratio = high_ela_pixels / total_pixels if total_pixels > 0 else 0.0

        # Normalize ELA score
        ela_score = min(1.0, ela_mean * 10 + suspicious_ratio * 0.5)

        return {
            "ela_score": round(ela_score, 4),
            "suspicious_regions": high_ela_pixels,
            "ela_mean": round(ela_mean, 4),
            "ela_std": round(ela_std, 4),
            "suspicious_ratio": round(suspicious_ratio, 4),
            "available": True,
        }
    except Exception as e:
        return {"ela_score": 0.0, "suspicious_regions": 0, "available": False, "error": str(e)}
