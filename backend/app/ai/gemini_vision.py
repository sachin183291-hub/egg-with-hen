"""
Gemini Vision Detector — egg & tray counting via Google Gemini AI.

This implements the ImageDetector interface using the free Gemini API
as a replacement for OpenAI.
"""
import json
import logging
from typing import Any, Optional

from app.ai.detector_interface import ImageDetector
from app.ai.openai_vision import SYSTEM_INSTRUCTION, CHAT_SYSTEM_INSTRUCTION, _normalise_enum

logger = logging.getLogger(__name__)

class GeminiVisionDetector(ImageDetector):
    """
    Egg & tray counter using Google Gemini Vision API.
    Implements the ImageDetector interface for drop-in replacement.
    """

    def __init__(self) -> None:
        from app.config import settings
        # pyrefly: ignore [missing-import]
        import google.generativeai as genai

        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Add it to backend/.env: GEMINI_API_KEY=your-gemini-key"
            )

        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = genai.GenerativeModel('gemini-flash-lite-latest')

    def analyze(self, image_bytes: bytes, mime_type: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Send the image to Gemini and return a structured count result.
        """
        try:
            image_parts = [
                {
                    "mime_type": mime_type,
                    "data": image_bytes
                }
            ]
            
            target_str = "eggs, egg trays, and hens"
            if target == "eggs":
                target_str = "ONLY eggs (count all real physical eggs AND all hand-drawn ovals/circles/egg sketches accurately into egg_count)"
            elif target == "hens":
                target_str = "ONLY hens/chickens (count all real live hens/chickens AND all hand-drawn chicken doodles/cartoons/sketches accurately into hen_count)"
            elif target == "trays":
                target_str = "ONLY egg trays (count all real egg trays, stack layers, AND all hand-drawn tray grids/matrices/cartons accurately into tray_count)"
                
            prompt = (
                f"{SYSTEM_INSTRUCTION}\n\n"
                "Please analyze this image carefully.\n"
                f"Target: {target_str}.\n"
                "Count both real physical objects and any hand-drawn/synthetic test shapes accurately.\n"
                "Return your answer as the JSON object described in the instructions with exact integer values for egg_count, tray_count, and hen_count."
            )
            
            response = self._model.generate_content(
                [prompt, image_parts[0]],
                generation_config={"temperature": 0.0}
            )

            raw_text = response.text.strip()
            logger.debug("Gemini raw response: %s", raw_text[:500])

            return self._parse_and_validate(raw_text)

        except Exception as exc:
            logger.error("Gemini Vision API error: %s", exc, exc_info=True)
            raise

    def chat_analyze(self, message: str, image_bytes: Optional[bytes], mime_type: str = "image/jpeg") -> dict:
        """
        Answer a user question about an image (conversational mode) using Gemini.
        """
        content = [CHAT_SYSTEM_INSTRUCTION, message]

        if image_bytes:
            content.append({
                "mime_type": mime_type,
                "data": image_bytes
            })

        try:
            response = self._model.generate_content(
                content,
                generation_config={"temperature": 0.3}
            )

            reply_text = response.text.strip()

            # If image was provided, also run a full structured analysis in parallel
            analysis = None
            if image_bytes:
                try:
                    analysis = self.analyze(image_bytes, mime_type)
                except Exception as e:
                    logger.warning("Structured analysis failed during chat: %s", e)

            return {"reply": reply_text, "analysis": analysis}

        except Exception as exc:
            logger.error("Gemini chat analyze error: %s", exc, exc_info=True)
            raise

    def analyze_dual(self, top_image_bytes: bytes, side_image_bytes: bytes, mime_type_top: str = "image/jpeg", mime_type_side: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Analyze dual images (top view and side view) to count trays.
        """
        try:
            image_parts = [
                {
                    "mime_type": mime_type_top,
                    "data": top_image_bytes
                },
                {
                    "mime_type": mime_type_side,
                    "data": side_image_bytes
                }
            ]
            
            prompt = (
                f"{SYSTEM_INSTRUCTION}\n\n"
                "You are provided with TWO images. The FIRST image is the TOP VIEW. The SECOND image is the SIDE VIEW.\n"
                "To correctly count the egg trays, STRICTLY follow these rules:\n"
                "1. Look at the SIDE VIEW (second image) and count how many trays are placed in a single vertical stack. Usually, there will be 1 tray visible on top and 19 trays underneath it, making exactly 20 trays per stack.\n"
                "2. Look at the TOP VIEW (first image) and count how many individual stacks of trays are visible.\n"
                "3. Multiply the number of stacks from the Top View by the number of trays in a single stack from the Side View (e.g. 20) to get the total `tray_count`.\n"
                "4. Calculate the total `egg_count` as EXACTLY: `tray_count` * 30 (since each tray holds 30 eggs).\n"
                "Count both real physical objects and any hand-drawn/synthetic test shapes accurately. DO NOT guess the tray count. Calculate carefully.\n"
                "Return your answer as the JSON object described in the instructions with exact integer values for egg_count, tray_count, and hen_count."
            )
            
            response = self._model.generate_content(
                [prompt, image_parts[0], image_parts[1]],
                generation_config={"temperature": 0.0}
            )

            raw_text = response.text.strip()
            logger.debug("Gemini dual analyze raw response: %s", raw_text[:500])

            return self._parse_and_validate(raw_text)

        except Exception as exc:
            logger.error("Gemini dual analyze error: %s", exc, exc_info=True)
            raise

    def _parse_and_validate(self, raw_text: str) -> dict:
        """Parse Gemini response text and validate/normalise it."""
        cleaned = raw_text
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                ln for ln in lines
                if not ln.strip().startswith("```")
            ).strip()

        try:
            data: dict = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Gemini JSON: %s\nRaw text: %s", exc, raw_text[:300])
            raise ValueError(f"Gemini returned invalid JSON: {exc}") from exc

        result = {
            "success": bool(data.get("success", True)),
            "egg_count": int(data.get("egg_count", 0)),
            "tray_count": int(data.get("tray_count", 0)),
            "hen_count": int(data.get("hen_count", 0)),
            "tray_types": {
                "green_plastic": int((data.get("tray_types") or {}).get("green_plastic", 0)),
                "paper_cardboard": int((data.get("tray_types") or {}).get("paper_cardboard", 0)),
                "other": int((data.get("tray_types") or {}).get("other", 0)),
                "unknown": int((data.get("tray_types") or {}).get("unknown", 0)),
            },
            "confidence": _normalise_enum(
                data.get("confidence", "medium"), ["high", "medium", "low"], "medium"
            ),
            "image_quality": _normalise_enum(
                data.get("image_quality", "fair"), ["good", "fair", "poor"], "fair"
            ),
            "notes": str(data.get("notes", "")),
        }

        types_total = sum(result["tray_types"].values())
        if types_total != result["tray_count"] and types_total > 0:
            result["tray_types"]["unknown"] += result["tray_count"] - types_total

        return result
