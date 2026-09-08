import json
import logging
import base64
from typing import Dict, Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert digital forensics AI. 
Your ONLY job is to detect if a photo is a "Screen Recapture". 
A "Screen Recapture" means the user took a picture OF a digital screen (like a computer monitor, laptop screen, or mobile phone screen) using a camera.

CRITICAL RULES:
1. If the photo shows a Web Browser (Chrome, Safari, etc.), a website dashboard, or computer software, IT IS A SCREEN RECAPTURE. You MUST return true.
2. If the photo shows a computer desktop, taskbar, or monitor bezels, IT IS A SCREEN RECAPTURE. You MUST return true.
3. If the photo is of a natural, physical room/scene, and there just happens to be a laptop sitting on a desk in the background, mark it as FALSE. We only flag it if the screen itself is the main subject being photographed.
4. IGNORE any Geotag text, maps, or timestamps overlaid on the bottom of the image. These are app overlays.

Return a JSON object with this exact schema:
{
    "is_screen_recapture": true/false,
    "confidence": 0.0 to 1.0,
    "reason": "Detailed step-by-step reasoning based on the RULES."
}
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
            
        model = genai.GenerativeModel("models/gemini-3.5-flash-lite")
        
        image_parts = [
            {"mime_type": mime_type, "data": image_bytes}
        ]
        
        response = model.generate_content(
            [SYSTEM_PROMPT, image_parts[0]],
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        raw_text = response.text.strip()
        data = json.loads(raw_text)
        is_screen = bool(data.get("is_screen_recapture", False))
        return {
            "is_screen_recapture": is_screen,
            "confidence": float(data.get("confidence", 0.0)),
            "reason": str(data.get("reason", "")),
            "error": False
        }
    except Exception as e:
        logger.error(f"Authenticity check failed: {e}")
        return {"is_screen_recapture": False, "confidence": 0.0, "reason": str(e), "error": True}
