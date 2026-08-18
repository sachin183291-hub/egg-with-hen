import os
import cv2
import numpy as np
import asyncio
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), ".env")))

import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.ai.gemini_vision import GeminiVisionDetector

def create_mixed_drawn_image():
    # Canvas with 4 drawn eggs, 1 drawn tray grid, and 2 drawn chickens
    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    
    # 4 eggs (ovals)
    for i in range(4):
        cv2.ellipse(img, (80 + i * 70, 100), (25, 38), 0, 0, 360, (0, 0, 0), 2)
        
    # 1 tray grid (3x3 grid)
    cv2.rectangle(img, (400, 60), (700, 250), (0, 150, 0), 3)
    for i in range(1, 3):
        cv2.line(img, (400, 60 + i * 63), (700, 60 + i * 63), (0, 150, 0), 2)
        cv2.line(img, (400 + i * 100, 60), (400 + i * 100, 250), (0, 150, 0), 2)
        
    # 2 hens
    for idx, x_c in enumerate([200, 500]):
        cv2.circle(img, (x_c, 450), 35, (0, 0, 0), 2) # body
        cv2.circle(img, (x_c + 25, 410), 18, (0, 0, 0), 2) # head
        pts_beak = np.array([[x_c + 43, 410], [x_c + 55, 414], [x_c + 43, 418]], np.int32)
        cv2.fillPoly(img, [pts_beak], (0, 165, 255))
        pts_comb = np.array([[x_c + 20, 392], [x_c + 28, 382], [x_c + 36, 392]], np.int32)
        cv2.fillPoly(img, [pts_comb], (0, 0, 255))
        cv2.line(img, (x_c - 10, 485), (x_c - 10, 520), (0, 0, 0), 2)
        cv2.line(img, (x_c + 10, 485), (x_c + 10, 520), (0, 0, 0), 2)
        
    cv2.imwrite("test_drawn_mixed.jpg", img)
    print("Created test_drawn_mixed.jpg")

async def main():
    create_mixed_drawn_image()
    detector = GeminiVisionDetector()
    with open("test_drawn_mixed.jpg", "rb") as f:
        img_bytes = f.read()
        
    print("\n--- Testing Mixed Image (General Count) ---")
    res = detector.analyze(img_bytes, "image/jpeg", "all")
    print("Result:", res)

if __name__ == "__main__":
    asyncio.run(main())
