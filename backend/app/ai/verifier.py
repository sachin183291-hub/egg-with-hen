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
    ELA_SUSPICIOUS_THRESHOLD = 0.35
    ELA_REVIEW_THRESHOLD = 0.20
    NOISE_SUSPICIOUS_THRESHOLD = 0.45
    NOISE_REVIEW_THRESHOLD = 0.25

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

        # Step 4: Aggregate scores (weighted)
        ela_weight = 0.6
        noise_weight = 0.4
        combined_score = ela_score * ela_weight + noise_score * noise_weight

        # Step 5: Determine status
        if combined_score >= self.ELA_SUSPICIOUS_THRESHOLD or noise_score >= self.NOISE_SUSPICIOUS_THRESHOLD:
            status = "SUSPICIOUS"
            message = (
                "AI-assisted verification: Potential image manipulation detected. "
                "Anomalous compression artifacts and/or noise patterns identified. "
                "Manual review by a qualified examiner is strongly recommended."
            )
            confidence = min(0.95, 0.5 + combined_score * 0.5)
        elif combined_score >= self.ELA_REVIEW_THRESHOLD or noise_score >= self.NOISE_REVIEW_THRESHOLD:
            status = "REVIEW_REQUIRED"
            message = (
                "AI-assisted verification: Inconclusive analysis. "
                "Some anomalies detected that require human review. "
                "Cannot confirm or deny manipulation."
            )
            confidence = min(0.80, 0.4 + combined_score * 0.4)
        else:
            status = "VERIFIED"
            message = (
                "AI-assisted verification: No significant manipulation indicators detected. "
                "Image compression artifacts and noise patterns appear consistent with "
                "unmodified camera output. Note: This is a heuristic analysis, not cryptographic proof."
            )
            confidence = min(0.95, 0.7 + (1 - combined_score) * 0.25)

        return {
            "status": status,
            "tamper_probability": round(combined_score, 4),
            "confidence": round(confidence, 4),
            "message": message,
            "details": {
                "ela_score": ela_score,
                "noise_score": noise_score,
                "combined_score": round(combined_score, 4),
                "ela_details": ela_result,
                "noise_details": noise_result,
                "metadata_consistent": True,
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
