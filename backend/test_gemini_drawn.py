import os
import asyncio
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), ".env")))

import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.ai.gemini_vision import GeminiVisionDetector

async def main():
    detector = GeminiVisionDetector()
    
    print("\n--- TEST 1: 5 DRAWN EGGS (target=eggs) ---")
    with open("test_drawn_eggs.jpg", "rb") as f:
        img_bytes = f.read()
    res1 = detector.analyze(img_bytes, "image/jpeg", "eggs")
    print("Result:", res1)

    print("\n--- TEST 2: 2 DRAWN TRAYS (target=trays) ---")
    with open("test_drawn_trays.jpg", "rb") as f:
        img_bytes = f.read()
    res2 = detector.analyze(img_bytes, "image/jpeg", "trays")
    print("Result:", res2)

    print("\n--- TEST 3: 3 DRAWN HENS (target=hens) ---")
    with open("test_drawn_hens.jpg", "rb") as f:
        img_bytes = f.read()
    res3 = detector.analyze(img_bytes, "image/jpeg", "hens")
    print("Result:", res3)

if __name__ == "__main__":
    asyncio.run(main())
