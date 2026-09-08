import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert digital forensics AI.
Your task is to determine if the user is trying to cheat by taking a photograph OF an image displayed on a digital screen (a screen recapture).

CRITICAL RULE: Mark "is_screen_recapture" as true ONLY if:
1. The photograph is clearly taken OF a digital screen (e.g., you are looking at a photo displayed on a monitor, laptop, tablet, or phone screen).
2. You see clear evidence of screen recapture, such as screen bezels framing the entire image, pixel grids, screen glare over the image, or moiré patterns.

EXCEPTIONS (DO NOT MARK AS TRUE FOR THESE):
- If there is simply a laptop, mobile phone, or monitor sitting in the background or on a desk in a normal room, DO NOT mark it as true. We only care if the MAIN SUBJECT is an image on a screen.
- IGNORE any digitally added Geotag overlays, timestamps, map snippets, or text at the bottom/corners of the image. These are app overlays, not screens.
- Bedsheets, clothes, or checkered fabrics are NOT screens.

Return a JSON object with this exact schema:
{
    "is_screen_recapture": true/false,
    "confidence": 0.0 to 1.0,
    "reason": "Brief explanation of what you see."
}
Respond ONLY with the JSON object, no markdown or extra text.
"""

def check_image_authenticity(image_bytes: bytes) -> Dict[str, Any]:
    try:
        from app.config import settings
        import google.generativeai as genai
        
        if not settings.GEMINI_API_KEY or len(settings.GEMINI_API_KEY.strip()) < 10:
            return {"is_screen_recapture": False, "confidence": 0.0, "reason": "No Gemini API key configured", "error": True}
            
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Determine MIME type heuristically
        mime_type = "image/jpeg"
        if image_bytes.startswith(b'\x89PNG'):
            mime_type = "image/png"
        elif image_bytes.startswith(b'RIFF') and b'WEBP' in image_bytes[8:12]:
            mime_type = "image/webp"
            
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        
        image_parts = [
            {"mime_type": mime_type, "data": image_bytes}
        ]
        
        response = model.generate_content([SYSTEM_PROMPT, image_parts[0]])
        
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join([ln for ln in lines if not ln.strip().startswith("```")]).strip()
            
        data = json.loads(raw_text)
        is_screen = bool(data.get("contains_device_or_screen", data.get("is_screen_recapture", False)))
        return {
            "is_screen_recapture": is_screen,
            "confidence": float(data.get("confidence", 0.0)),
            "reason": str(data.get("reason", "")),
            "error": False
        }
    except Exception as e:
        logger.error(f"Authenticity check failed: {e}")
        return {"is_screen_recapture": False, "confidence": 0.0, "reason": str(e), "error": True}
