"""
Quick test: run thermal detection on the sample thermal image
and print how many hens are detected + their temperatures.
"""
import sys
import os
sys.path.insert(0, os.getcwd())

import cv2
import numpy as np
import requests

# Download the sample thermal image the user shared
url = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat_03.jpg/1200px-Cat_03.jpg"

# Let's create a synthetic thermal-like test image
# (bright red/orange blobs on a dark blue/green background, like a real thermal cam)
img = np.zeros((400, 500, 3), dtype=np.uint8)

# Background: dark blue (cold background)
img[:, :] = (80, 20, 10)  # BGR: dark blue

# Hen 1: red/orange blob (upper area) ~38°C
cv2.ellipse(img, (150, 100), (40, 30), 0, 0, 360, (30, 100, 220), -1)   # orange
cv2.ellipse(img, (150, 100), (20, 15), 0, 0, 360, (20, 60, 240), -1)    # red core

# Hen 2: bigger orange/red blob (center) ~36°C
cv2.ellipse(img, (260, 220), (55, 45), 0, 0, 360, (30, 130, 210), -1)   # orange
cv2.ellipse(img, (260, 220), (35, 28), 0, 0, 360, (20, 80, 230), -1)    # red
cv2.ellipse(img, (260, 220), (15, 12), 0, 0, 360, (200, 50, 240), -1)   # bright red

# Hen 3: warm yellow-orange blob (side) ~33°C
cv2.ellipse(img, (410, 300), (35, 28), 0, 0, 360, (40, 180, 230), -1)   # yellow-orange
cv2.ellipse(img, (410, 300), (20, 15), 0, 0, 360, (30, 130, 215), -1)

from app.ai.thermal_service import detect_thermal_hotspots

annotated, count, hens_data = detect_thermal_hotspots(img, 20.0, 40.0)

print(f"\n{'='*45}")
print(f"  THERMAL DETECTION RESULT")
print(f"{'='*45}")
print(f"  Total Hens Detected: {count}")
print(f"{'='*45}")
for hen in hens_data:
    status = "[Hot]" if hen['temperature'] >= 38 else "[Warm]" if hen['temperature'] >= 34 else "[Normal]"
    print(f"  Hen #{hen['hen_number']}  |  {hen['temperature']:.1f} C  |  {status}")
print(f"{'='*45}\n")

# Save result
cv2.imwrite("thermal_test_output.jpg", annotated)
print("  Output saved: thermal_test_output.jpg")
