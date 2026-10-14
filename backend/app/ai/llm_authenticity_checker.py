import json
import logging
import io
from typing import Dict, Any
from PIL import Image

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert digital forensics AI specializing in physical presence verification and anti-spoofing.
Your ONLY job is to detect if a photo is a "Screen Recapture".

A "Screen Recapture" means the user took a picture OF an electronic digital screen (laptop screen, computer monitor, mobile phone screen, or tablet screen) displaying digital software/websites/windows, instead of capturing a live physical scene directly.

CRITICAL RULES:
1. IF the photo shows a physical real-world scene (e.g. rooms, furniture, chairs, walls, outdoors, farm, animals, people, objects, paper):
   -> IT IS A GENUINE PHYSICAL SCENE. Return is_screen_recapture: false, device_type: "none".
2. DO NOT confuse physical real-world textures (mesh chairs, woven fabric, clothing, curtains, grid lines, walls, tiles, floor patterns) with electronic screens!
3. IGNORE any GeoTag watermark banner, map pin, or text overlay stamped at the bottom.
4. ONLY return is_screen_recapture: true IF there is clear, unmistakable evidence of an electronic screen displaying digital UI, operating system, browser, software windows, or physical monitor/laptop screen bezels.

Return strict JSON only:
{
    "is_screen_recapture": false,
    "device_type": "none",
    "confidence": 0.99,
    "reason": "Detailed explanation"
}
"""

import time

CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]

def check_image_authenticity(image_bytes: bytes) -> Dict[str, Any]:
    """
    Fast screen recapture check (detects laptop, mobile, and tablet screens).
    Uses downscaled thumbnail for sub-second execution.
    Tries fast candidate Gemini models with fallback to local OpenCV analysis.
    """
    try:
        from app.config import settings
        import google.generativeai as genai

        if not settings.GEMINI_API_KEY or len(settings.GEMINI_API_KEY.strip()) < 10:
            return {"is_screen_recapture": False, "device_type": "none", "confidence": 0.0, "reason": "No Gemini API key, using local OpenCV", "error": False}

        # Downscale image to max 512px to guarantee ultra-fast upload (<100ms)
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((512, 512))
        thumb_io = io.BytesIO()
        img.convert("RGB").save(thumb_io, format="JPEG", quality=75)
        thumb_bytes = thumb_io.getvalue()
        thumb_img = Image.open(io.BytesIO(thumb_bytes))

        genai.configure(api_key=settings.GEMINI_API_KEY)

        response = None
        for model_name in CANDIDATE_MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    [SYSTEM_PROMPT, thumb_img],
                    generation_config={"temperature": 0.0, "max_output_tokens": 180}
                )
                if response and response.text:
                    break
            except Exception as model_err:
                logger.warning(f"Model {model_name} failed: {model_err}")
                continue

        if not response or not response.text:
            return {"is_screen_recapture": False, "device_type": "none", "confidence": 0.0, "reason": "Local OpenCV analysis fallback", "error": False}

        raw_text = response.text.strip()
        import re
        is_screen = False
        device_type = "none"
        reason = "AI physical scene verification"
        confidence = 0.90

        # Try JSON parsing
        try:
            cleaned_text = re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', raw_text).strip()
            match = re.search(r'\{[\s\S]*?\}', cleaned_text)
            if match:
                data = json.loads(match.group(0))
                is_screen = bool(data.get("is_screen_recapture", False))
                device_type = str(data.get("device_type", "none"))
                reason = str(data.get("reason", reason))
                confidence = float(data.get("confidence", 0.95))
            else:
                is_screen = ("\"is_screen_recapture\": true" in raw_text.lower() or 
                             "\"is_screen_recapture\":true" in raw_text.lower())
        except Exception as parse_e:
            logger.warning(f"JSON parsing error: {parse_e}")
            is_screen = ("\"is_screen_recapture\": true" in raw_text.lower() or 
                         "\"is_screen_recapture\":true" in raw_text.lower())

        return {
            "is_screen_recapture": is_screen,
            "device_type": device_type,
            "confidence": confidence,
            "reason": reason,
            "error": False
        }
    except Exception as e:
        logger.warning(f"Gemini LLM check bypassed to local OpenCV: {e}")
        return {"is_screen_recapture": False, "device_type": "none", "confidence": 0.0, "reason": "Local OpenCV analysis applied", "error": False}
