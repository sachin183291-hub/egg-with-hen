import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert digital forensics AI. 
Your ONLY job is to detect if a photo is a "Screen Recapture". 
A "Screen Recapture" means the user took a photo of an image displayed on a digital screen (like a monitor, laptop, or mobile phone) to fake a live photo.

ANALYSIS STEPS:
1. Identify the MAIN SUBJECT of the photo.
2. Is the main subject being displayed on a screen? Look for screen bezels framing the image, pixel grids, or screen glare.
3. If yes, it is a screen recapture.
4. If the photo is just a normal room/scene, and there happens to be a laptop or mobile phone sitting on a table in the background, THIS IS NOT A SCREEN RECAPTURE. The device is just part of the scene. Do NOT flag it.
5. IGNORE any Geotag text, maps, or timestamps overlaid on the image. These are app overlays.

Return a JSON object with this exact schema:
{
    "is_screen_recapture": true/false,
    "confidence": 0.0 to 1.0,
    "reason": "Detailed step-by-step reasoning based on the ANALYSIS STEPS."
}
Respond ONLY with valid JSON.
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
