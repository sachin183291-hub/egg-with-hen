import logging
from typing import Optional

from app.ai.detector_interface import ImageDetector
from app.ai.yolo_service import detect_objects

logger = logging.getLogger(__name__)

class CustomYOLODetector(ImageDetector):
    """
    Egg & tray counter using local YOLO model.
    Implements the ImageDetector interface for drop-in replacement.
    """

    def analyze(self, image_bytes: bytes, mime_type: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Send the image to YOLO service and return a structured count result.
        """
        try:
            results = detect_objects(image_bytes)
            
            # Map YOLO output to EggAnalysisResponse schema
            conf_val = results.get("confidence", 0.0)
            if conf_val > 0.7:
                confidence_str = "high"
            elif conf_val > 0.4:
                confidence_str = "medium"
            else:
                confidence_str = "low"
                
            return {
                "success": True,
                "egg_count": results.get("egg_count", 0),
                "tray_count": results.get("tray_count", 0),
                "hen_count": results.get("hen_count", 0),
                "tray_types": {
                    "green_plastic": 0,
                    "paper_cardboard": 0,
                    "other": 0,
                    "unknown": results.get("tray_count", 0)
                },
                "confidence": confidence_str,
                "image_quality": "good",
                "notes": "Detected using local YOLO model."
            }
        except Exception as exc:
            logger.error("YOLO detection error: %s", exc, exc_info=True)
            raise

    def chat_analyze(self, message: str, image_bytes: Optional[bytes], mime_type: str = "image/jpeg") -> dict:
        """
        Conversational chat analysis. Since YOLO is not a LLM, we return a canned response with counts.
        """
        analysis = None
        if image_bytes:
            analysis = self.analyze(image_bytes, mime_type)
            reply = f"Based on the image, I counted {analysis['egg_count']} eggs, {analysis['tray_count']} trays, and {analysis['hen_count']} hens using our local AI model."
        else:
            reply = "I'm a local object detection model. Please upload an image for me to count eggs or trays."
            
    def analyze_dual(self, top_image_bytes: bytes, side_image_bytes: bytes, mime_type_top: str = "image/jpeg", mime_type_side: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Analyze dual images (top view and side view) using YOLO.
        Since YOLO works on a single image, we can just analyze the top view and side view separately
        and combine the results, or just analyze the side view to count stacks.
        """
        try:
            top_results = detect_objects(top_image_bytes)
            side_results = detect_objects(side_image_bytes)
            
            # Simple heuristic: YOLO counts all trays.
            # Assuming side view gives us stacks or trays directly.
            tray_count = side_results.get("tray_count", 0) + top_results.get("tray_count", 0)
            egg_count = tray_count * 30
            
            return {
                "success": True,
                "egg_count": egg_count,
                "tray_count": tray_count,
                "hen_count": 0,
                "tray_types": {
                    "green_plastic": 0,
                    "paper_cardboard": 0,
                    "other": 0,
                    "unknown": tray_count
                },
                "confidence": "medium",
                "image_quality": "good",
                "notes": "Detected using local YOLO model."
            }
        except Exception as exc:
            logger.error("YOLO dual detection error: %s", exc, exc_info=True)
            raise
