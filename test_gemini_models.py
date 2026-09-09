import sys
import os
import asyncio
from dotenv import load_dotenv

load_dotenv(os.path.abspath("backend/.env"))

import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def test_model(model_name):
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Hello")
        print(f"{model_name}: SUCCESS")
    except Exception as e:
        print(f"{model_name}: FAILED - {e}")

async def main():
    await test_model("models/gemini-2.5-flash")
    await test_model("models/gemini-2.5-flash-lite")
    await test_model("models/gemini-3.5-flash-lite")
    await test_model("models/gemini-3.1-flash-lite")
    
if __name__ == "__main__":
    asyncio.run(main())
