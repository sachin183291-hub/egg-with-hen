import cv2
import numpy as np
from app.ai.thermal_service import process_thermal_hotspots

# Create a dummy grayscale image (dark background, some bright spots)
img = np.zeros((200, 200, 3), dtype=np.uint8)
img[:,:] = (50, 50, 50) # background

# Draw some "hens" (bright spots)
cv2.circle(img, (50, 50), 5, (200, 200, 200), -1) # Intensity 200 -> Temp 39.2
cv2.circle(img, (100, 100), 10, (150, 150, 150), -1) # Intensity 150 -> Temp 29.4
cv2.circle(img, (150, 150), 2, (255, 255, 255), -1) # Intensity 255 -> Temp 50 (should be excluded)

annotated, count = process_thermal_hotspots(img, 20.0, 40.0)
print(f"Hens detected: {count}")
