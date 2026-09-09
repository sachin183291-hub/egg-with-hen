import sys
import os
import asyncio
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv(os.path.abspath("backend/.env"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def test_lite_vision():
    try:
        model = genai.GenerativeModel("models/gemini-3.5-flash-lite")
        with open("backend/test_drawn_eggs.jpg", "rb") as f:
            image_bytes = f.read()
        response = model.generate_content([
            "What is in this image?",
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
        print("Lite Vision SUCCESS:", response.text.strip())
    except Exception as e:
        print("Lite Vision FAILED:", e)

if __name__ == "__main__":
    asyncio.run(test_lite_vision())
