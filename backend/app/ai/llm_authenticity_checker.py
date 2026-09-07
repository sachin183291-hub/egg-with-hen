import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert digital forensics AI.
Your task is to determine if the provided image is a genuine photograph of a real physical scene/object OR if it is a 'Screen Recapture'.
A 'Screen Recapture' means the photo was taken of a digital screen (like a smartphone, tablet, laptop, or monitor).

CRITICAL RULE: Be EXTREMELY STRICT. If even a tiny portion of a laptop bezel, keyboard, mobile phone edge, monitor frame, or screen glare is visible anywhere in the image (especially at the edges), you MUST mark "is_screen_recapture" as true.

Look closely for:
- Any visible laptop/mobile/tablet physical borders, bezels, or keyboards in the background or edges
- Moiré patterns (rainbow or wavy interference patterns on screens)
- Visible pixel grid or subpixels
- Screen glare, reflections, or smudges on glass
- Unnatural lighting or contrast typical of backlit screens

If it looks like a normal camera photo with absolutely no screen elements, it is genuine.

Return a JSON object with this exact schema:
{
    "is_screen_recapture": true/false,
    "confidence": 0.0 to 1.0,
    "reason": "Brief explanation of what you see that proves it is or isn't a screen recapture."
}
Respond ONLY with the JSON object, no markdown or extra text.
"""

def check_image_authenticity(image_bytes: bytes) -> Dict[str, Any]:
    try:
        from app.config import settings
        import google.generativeai as genai
        
        if not settings.GEMINI_API_KEY or len(settings.GEMINI_API_KEY.strip()) < 10:
            return {"is_screen_recapture": False, "confidence": 0.0, "reason": "No Gemini API key configured"}
            
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
        return {
            "is_screen_recapture": bool(data.get("is_screen_recapture", False)),
            "confidence": float(data.get("confidence", 0.0)),
            "reason": str(data.get("reason", ""))
        }
    except Exception as e:
        logger.error(f"Authenticity check failed: {e}")
        return {"is_screen_recapture": False, "confidence": 0.0, "reason": str(e)}
