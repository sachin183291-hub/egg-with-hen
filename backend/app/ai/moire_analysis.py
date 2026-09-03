import cv2
import numpy as np
from typing import Dict, Any

def perform_moire_analysis(image_bytes: bytes) -> Dict[str, Any]:
    """
    Detects if the image is a photo of a screen (recapture) by analyzing Moiré patterns.
    Uses Fast Fourier Transform (FFT) to find high-frequency periodic noise typical of pixel grids.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"moire_score": 0.0, "is_screen": False, "error": "Invalid image"}
        
        # Resize to standard size for consistent frequency analysis
        img = cv2.resize(img, (512, 512))
        
        # Calculate FFT
        f = np.fft.fft2(img)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1)
        
        # Create a mask to block the low frequencies (center) and axes
        rows, cols = img.shape
        crow, ccol = rows // 2, cols // 2
        
        mask = np.ones((rows, cols), np.uint8)
        # Block center (low frequencies - natural image features)
        r = 40
        cv2.circle(mask, (ccol, crow), r, 0, -1)
        
        # Block vertical and horizontal axes (common in all images)
        thickness = 15
        mask[crow-thickness:crow+thickness, :] = 0
        mask[:, ccol-thickness:ccol+thickness] = 0
        
        # Apply mask
        masked_spectrum = magnitude_spectrum * mask
        
        # Threshold to find peaks
        valid_pixels = masked_spectrum[mask > 0]
        mean_val = np.mean(valid_pixels)
        std_val = np.std(valid_pixels)
        
        # Detect sharp peaks which indicate periodic grid patterns
        threshold = mean_val + 4 * std_val
        peaks = np.sum(masked_spectrum > threshold)
        
        # Normalize score (Cap at 1.0)
        # A real screen photo typically has hundreds of strong high-frequency peaks
        score = float(min(1.0, peaks / 500.0))
        
        return {
            "moire_score": score,
            "peaks_found": int(peaks),
            "is_screen": score > 0.4
        }
    except Exception as e:
        return {"moire_score": 0.0, "is_screen": False, "error": str(e)}
