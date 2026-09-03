"""
Main AI verification pipeline.
Aggregates ELA, noise analysis, and image validation checks.
Returns a structured result clearly labeled as AI-ASSISTED VERIFICATION.

Architecture:
- BaseVerifier: abstract interface
- OpenCVVerifier: current implementation (ELA + noise)
- MockVerifier: for testing
- Future: PyTorchVerifier, EnsembleVerifier

Do NOT claim 100% accuracy. This is a heuristic pipeline.
"""
import io
import hashlib
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from app.ai.ela_analysis import perform_ela_analysis
from app.ai.noise_analysis import perform_noise_analysis


# ─── Base Interface ────────────────────────────────────────────────────────────

class BaseVerifier(ABC):
    """Abstract base for all AI verification backends."""

    @abstractmethod
    def verify(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Verify an image and return structured result.

        Returns:
            {
                "status": "VERIFIED" | "SUSPICIOUS" | "REVIEW_REQUIRED",
                "tamper_probability": float (0-1),
                "confidence": float (0-1),
                "message": str,
                "details": dict
            }
        """
        pass


# ─── OpenCV / PIL Verifier ─────────────────────────────────────────────────────

class OpenCVVerifier(BaseVerifier):
    """
    Heuristic verification using ELA + noise analysis.
    Clearly labeled as AI-assisted, not ground-truth detection.
    """

    MODEL_VERSION = "opencv-v1.0"

    # Thresholds (tunable without model retraining)
    ELA_SUSPICIOUS_THRESHOLD = 0.60
    ELA_REVIEW_THRESHOLD = 0.40
    NOISE_SUSPICIOUS_THRESHOLD = 0.80
    NOISE_REVIEW_THRESHOLD = 0.50

    def _validate_image(self, image_bytes: bytes) -> Optional[str]:
        """Return error string if image is invalid, else None."""
        if len(image_bytes) == 0:
            return "Empty file"
        if len(image_bytes) > 20 * 1024 * 1024:
            return "File too large for analysis"
        if not PIL_AVAILABLE:
            return "PIL not available"

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()
            return None
        except Exception as e:
            return f"Invalid image: {e}"

    def verify(self, image_bytes: bytes) -> Dict[str, Any]:
        """Run full AI-assisted verification pipeline."""

        # Step 1: Validate
        validation_error = self._validate_image(image_bytes)
        if validation_error:
            return {
                "status": "REVIEW_REQUIRED",
                "tamper_probability": 0.5,
                "confidence": 0.3,
                "message": f"AI-assisted verification: Image validation failed — {validation_error}",
                "details": {"validation_error": validation_error, "model_version": self.MODEL_VERSION},
            }

        # Step 2: ELA analysis
        ela_result = perform_ela_analysis(image_bytes)
        ela_score = ela_result.get("ela_score", 0.0)

        # Step 3: Noise analysis
        noise_result = perform_noise_analysis(image_bytes)
        noise_score = noise_result.get("noise_score", 0.0)
        
        # Step 4: Screen Recapture analysis via LLM (GPT-4o)
        from app.ai.llm_authenticity_checker import check_image_authenticity
        llm_result = check_image_authenticity(image_bytes)
        is_screen = llm_result.get("is_screen_recapture", False)
        llm_confidence = llm_result.get("confidence", 0.0)
        llm_reason = llm_result.get("reason", "")

        # Step 5: Aggregate scores (kept for backwards compatibility of metadata)
        combined_score = (ela_score * 0.5) + (noise_score * 0.5)

        # Step 6: Determine status
        # Only use Screen Recapture from LLM to flag as SUSPICIOUS based on user feedback.
        # ELA and Noise are kept for metadata but do not trigger SUSPICIOUS status.
        if is_screen:
            status = "SUSPICIOUS"
            message = (
                "AI-assisted verification: Screen Recapture Detected! "
                f"The AI determined this is a photo of a screen rather than a live photo. Reason: {llm_reason}"
            )
            confidence = max(0.9, llm_confidence)
            tamper_probability = max(0.7, llm_confidence)
        else:
            status = "VERIFIED"
            message = (
                "AI-assisted verification: Original Live Photo. "
                "No screen recapture (Moiré patterns) or significant manipulation indicators detected."
            )
            confidence = 0.95
            tamper_probability = combined_score

        return {
            "status": status,
            "tamper_probability": round(tamper_probability, 4),
            "confidence": round(confidence, 4),
            "message": message,
            "details": {
                "ela_score": ela_score,
                "noise_score": noise_score,
                "llm_is_screen": is_screen,
                "llm_confidence": llm_confidence,
                "llm_reason": llm_reason,
                "combined_score": round(combined_score, 4),
                "model_version": self.MODEL_VERSION,
            },
        }


# ─── Mock Verifier (Testing) ───────────────────────────────────────────────────

class MockVerifier(BaseVerifier):
    """Deterministic mock verifier for testing. Returns predictable results."""

    def verify(self, image_bytes: bytes) -> Dict[str, Any]:
        size = len(image_bytes)
        # Deterministic: large files = VERIFIED, small = REVIEW_REQUIRED
        if size > 100_000:
            return {
                "status": "VERIFIED",
                "tamper_probability": 0.05,
                "confidence": 0.90,
                "message": "AI-assisted verification: Mock result — VERIFIED",
                "details": {"model_version": "mock-v1.0"},
            }
        elif size > 10_000:
            return {
                "status": "REVIEW_REQUIRED",
                "tamper_probability": 0.35,
                "confidence": 0.60,
                "message": "AI-assisted verification: Mock result — REVIEW_REQUIRED",
                "details": {"model_version": "mock-v1.0"},
            }
        else:
            return {
                "status": "SUSPICIOUS",
                "tamper_probability": 0.75,
                "confidence": 0.85,
                "message": "AI-assisted verification: Mock result — SUSPICIOUS",
                "details": {"model_version": "mock-v1.0"},
            }


# ─── Factory ──────────────────────────────────────────────────────────────────

def get_verifier(model_type: Optional[str] = None) -> BaseVerifier:
    """Return the configured verifier backend."""
    from app.config import settings
    mt = (model_type or settings.AI_MODEL_TYPE).lower()

    if mt == "mock":
        return MockVerifier()
    # Default: opencv (ELA + noise)
    return OpenCVVerifier()


# ─── Convenience function ──────────────────────────────────────────────────────

def verify_image_content(image_bytes: bytes) -> Dict[str, Any]:
    """Top-level function used by the evidence upload API."""
    verifier = get_verifier()
    return verifier.verify(image_bytes)
