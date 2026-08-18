"""
Statistical noise analysis for image tamper detection.
Analyzes local noise patterns — manipulated regions often have different noise signatures.
"""
import io
import numpy as np
from typing import Dict, Any

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def perform_noise_analysis(image_bytes: bytes) -> Dict[str, Any]:
    """
    Analyze local noise variance across image regions.
    Artificially inserted content often has different noise characteristics
    than the surrounding image.

    Returns:
        noise_score: 0-1 (higher = more suspicious noise variance)
        noise_uniformity: how uniform noise is across image (higher = more natural)
    """
    if not PIL_AVAILABLE:
        return {"noise_score": 0.0, "noise_uniformity": 1.0, "available": False}

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")  # Grayscale
        arr = np.array(img, dtype=np.float32)

        # Divide image into grid of blocks
        h, w = arr.shape
        block_size = max(32, min(h, w) // 16)

        block_variances = []
        rows = max(1, h // block_size)
        cols = max(1, w // block_size)

        for r in range(rows):
            for c in range(cols):
                block = arr[r*block_size:(r+1)*block_size, c*block_size:(c+1)*block_size]
                if block.size > 0:
                    block_variances.append(float(np.var(block)))

        if not block_variances:
            return {"noise_score": 0.0, "noise_uniformity": 1.0, "available": True}

        variance_array = np.array(block_variances)
        mean_var = float(np.mean(variance_array))
        std_var = float(np.std(variance_array))

        # Coefficient of variation — high CV suggests inconsistent noise (tampering signal)
        cv = std_var / mean_var if mean_var > 0 else 0.0

        # Normalize noise score (CV > 1.5 is suspicious)
        noise_score = min(1.0, cv / 2.0)
        noise_uniformity = 1.0 - noise_score

        return {
            "noise_score": round(noise_score, 4),
            "noise_uniformity": round(noise_uniformity, 4),
            "block_variance_cv": round(cv, 4),
            "mean_block_variance": round(mean_var, 4),
            "available": True,
        }
    except Exception as e:
        return {"noise_score": 0.0, "noise_uniformity": 1.0, "available": False, "error": str(e)}
