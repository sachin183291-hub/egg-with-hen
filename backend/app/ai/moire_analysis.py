import cv2
import numpy as np
from typing import Dict, Any

def perform_moire_analysis(image_bytes: bytes) -> Dict[str, Any]:
    """
    Detects if the image is a photo of a screen (recapture from laptop, mobile, or tablet).
    Combines:
      1. Fast Fourier Transform (FFT) periodic grid & Moiré frequency peak detection.
      2. Rectangular display bezel & screen frame boundary analysis.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"moire_score": 0.0, "is_screen": False, "error": "Invalid image"}
        
        orig_h, orig_w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. FFT Moire Analysis
        resized = cv2.resize(gray, (512, 512)).astype(np.float32)
        f = np.fft.fft2(resized)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1)
        
        crow, ccol = 256, 256
        y_grid, x_grid = np.ogrid[:512, :512]
        center_dist = (x_grid - ccol)**2 + (y_grid - crow)**2
        
        # Mask out center (DC component and natural low frequencies)
        masked_spectrum = magnitude_spectrum.copy()
        masked_spectrum[center_dist <= 35**2] = 0
        
        # Mask horizontal and vertical axes (natural building/furniture/stamp edges)
        masked_spectrum[crow-8:crow+8, :] = 0
        masked_spectrum[:, ccol-8:ccol+8] = 0
        
        valid_pixels = masked_spectrum[(center_dist > 35**2) & (masked_spectrum > 0)]
        if len(valid_pixels) > 0:
            mean_val = float(np.mean(valid_pixels))
            std_val = float(np.std(valid_pixels))
            threshold = mean_val + 3.5 * std_val
            peaks = int(np.sum(valid_pixels > threshold))
            moire_score = float(min(1.0, peaks / 1500.0))
        else:
            mean_val, std_val = 0.0, 0.0
            peaks = 0
            moire_score = 0.0
        
        # 2. Rectangular Screen Frame / Bezel Detection
        has_screen_frame = False
        edges = cv2.Canny(gray, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        total_pixels = orig_h * orig_w
        for c in contours:
            area = cv2.contourArea(c)
            if area > (total_pixels * 0.18):  # Must occupy > 18% of photo
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.03 * peri, True)
                if len(approx) == 4:
                    x_b, y_b, cw, ch = cv2.boundingRect(approx)
                    aspect = max(cw, ch) / (min(cw, ch) + 1e-5)
                    # Typical monitor/laptop screen aspect ratios
                    if 1.25 <= aspect <= 2.2:
                        has_screen_frame = True
                        break
        
        # OpenCV fallback should only flag screen if there is both an unambiguous screen frame AND strong moire
        is_screen = has_screen_frame and (moire_score > 0.75 or peaks > 1000)
        
        return {
            "moire_score": round(moire_score, 4),
            "peaks_found": peaks,
            "has_screen_frame": has_screen_frame,
            "is_screen": is_screen
        }
    except Exception as e:
        return {"moire_score": 0.0, "is_screen": False, "error": str(e)}
