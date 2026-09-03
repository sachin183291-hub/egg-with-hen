"""
Detector interface and factory.

This module defines the ImageDetector abstract base class and a factory
function `get_detector()` that returns the configured provider.

Future usage:
    # In .env:
    DETECTOR_PROVIDER=yolo  →  returns CustomYOLODetector
    DETECTOR_PROVIDER=openai →  returns OpenAIVisionDetector
"""
import abc
from typing import Optional


class ImageDetector(abc.ABC):
    """Abstract base class for all image detection providers."""

    @abc.abstractmethod
    def analyze(self, image_bytes: bytes, mime_type: str, target: str = "trays") -> dict:
        """
        Analyze an image and return a structured count result.

        Args:
            image_bytes: Raw bytes of the uploaded image.
            mime_type: MIME type string, e.g. 'image/jpeg'.
            target: The detection target ('eggs', 'hens', 'trays').

        Returns:
            A dict conforming to EggAnalysisResponse schema:
            {
                "success": bool,
                "egg_count": int,
                "tray_count": int,
                "tray_types": {
                    "green_plastic": int,
                    "paper_cardboard": int,
                    "other": int,
                    "unknown": int
                },
                "confidence": "high" | "medium" | "low",
                "image_quality": "good" | "fair" | "poor",
                "notes": str
            }
        """
        ...

    @abc.abstractmethod
    def chat_analyze(self, message: str, image_bytes: Optional[bytes], mime_type: str = "image/jpeg") -> dict:
        """
        Conversational chat analysis.
        """
        ...

    @abc.abstractmethod
    def analyze_dual(self, top_image_bytes: bytes, side_image_bytes: bytes, mime_type_top: str = "image/jpeg", mime_type_side: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Analyze two images (top view and side view) to calculate the total tray count.
        """
        ...


def get_detector(provider: Optional[str] = None) -> ImageDetector:
    """
    Factory function: returns the correct ImageDetector based on the
    DETECTOR_PROVIDER environment variable (or explicit override).

    Supported providers:
        "openai"  → OpenAIVisionDetector (default)
        "yolo"    → CustomYOLODetector   (future custom model)
    """
    from app.config import settings

    selected = (provider or settings.DETECTOR_PROVIDER or "openai").lower()

    if selected == "openai":
        from app.ai.openai_vision import OpenAIVisionDetector
        return OpenAIVisionDetector()
        
    if selected == "gemini":
        try:
            from app.ai.gemini_vision import GeminiVisionDetector
            return GeminiVisionDetector()
        except RuntimeError:
            from app.ai.yolo_detector import CustomYOLODetector
            return CustomYOLODetector()

    if selected == "yolo":
        from app.ai.yolo_detector import CustomYOLODetector
        return CustomYOLODetector()

    raise ValueError(
        f"Unknown DETECTOR_PROVIDER: '{selected}'. "
        "Supported values: 'openai', 'gemini', 'yolo'"
    )
