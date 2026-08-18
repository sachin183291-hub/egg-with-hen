import os
import asyncio
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Load env before importing app modules
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "giotag project", "backend", ".env")))

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "giotag project", "backend")))

from app.ai.gemini_vision import GeminiVisionDetector

async def main():
    detector = GeminiVisionDetector()
    # Read the real image
    with open('test_eggs_synthetic.jpg', 'rb') as f:
        real_image = f.read()
    try:
        res = detector.analyze(real_image, "image/jpeg", "eggs")
        print("RESULT:", res)
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
