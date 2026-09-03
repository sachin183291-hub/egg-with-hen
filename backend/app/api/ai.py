"""AI verification API endpoints."""
from datetime import datetime
from typing import Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, Evidence, AIVerification, AuditActionEnum, AIStatusEnum, EvidenceStatusEnum
from app.schemas.schemas import AIVerifyResult
from app.security.rbac import get_current_user
from app.services.audit import log_action
from app.services.storage import storage

router = APIRouter(prefix="/api/ai", tags=["AI Verification"])


@router.post("/verify/{evidence_id}", response_model=AIVerifyResult)
async def verify_evidence(
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger AI verification on a specific evidence record."""
    ev = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.deleted_at == None).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Load image
    if ev.storage_url and isinstance(storage, __import__('app.services.storage', fromlist=['LocalStorageBackend']).LocalStorageBackend):
        img_path = storage.get_absolute_path(ev.storage_url)
        if img_path and img_path.exists():
            image_bytes = img_path.read_bytes()
        else:
            raise HTTPException(status_code=404, detail="Image file not found on storage")
    else:
        raise HTTPException(status_code=400, detail="Cannot access image for verification")

    from app.ai.verifier import verify_image_content
    result = verify_image_content(image_bytes)

    # Update AI record
    ai = db.query(AIVerification).filter(AIVerification.evidence_id == evidence_id).first()
    if not ai:
        ai = AIVerification(evidence_id=evidence_id)
        db.add(ai)

    ai.status = AIStatusEnum[result["status"]]
    ai.tamper_probability = result["tamper_probability"]
    ai.confidence_score = result["confidence"]
    ai.verification_message = result["message"]
    details = result.get("details", {})
    ai.ela_score = details.get("ela_score")
    ai.noise_score = details.get("noise_score")
    ai.metadata_consistent = details.get("metadata_consistent", True)
    ai.verified_at = datetime.utcnow()

    # Update evidence status
    status_map = {
        "VERIFIED": EvidenceStatusEnum.VERIFIED,
        "SUSPICIOUS": EvidenceStatusEnum.SUSPICIOUS,
        "REVIEW_REQUIRED": EvidenceStatusEnum.REVIEW_REQUIRED,
    }
    ev.status = status_map.get(result["status"], EvidenceStatusEnum.UPLOADED)

    log_action(
        db, AuditActionEnum.AI_VERIFIED,
        user_id=current_user.id, resource_type="evidence", resource_id=evidence_id,
        description=f"AI verification: {result['status']} (tamper_prob={result['tamper_probability']})",
        result="SUCCESS", request=request,
    )
    db.commit()

    return AIVerifyResult(**result)


@router.get("/result/{evidence_id}", response_model=AIVerifyResult)
async def get_ai_result(
    evidence_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the cached AI verification result for an evidence record."""
    ai = db.query(AIVerification).filter(AIVerification.evidence_id == evidence_id).first()
    if not ai:
        raise HTTPException(status_code=404, detail="No AI verification result found")

    return AIVerifyResult(
        status=ai.status.value,
        tamper_probability=ai.tamper_probability or 0.0,
        confidence=ai.confidence_score or 0.0,
        message=ai.verification_message or "No message available",
        details={
            "ela_score": ai.ela_score,
            "noise_score": ai.noise_score,
            "metadata_consistent": ai.metadata_consistent,
            "model_version": ai.model_version,
        },
    )

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, BackgroundTasks 
import time
import os
import subprocess

# ... existing code ...

def save_to_dataset_and_train(image_bytes: bytes, detections: list):
    try:
        import cv2
        import numpy as np
        
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return
            
        image_height, image_width = img.shape[:2]
        
        # Define paths
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../egg-detection-system"))
        dataset_dir = os.path.join(base_dir, "dataset")
        images_dir = os.path.join(dataset_dir, "images", "train")
        labels_dir = os.path.join(dataset_dir, "labels", "train")
        train_script = os.path.join(base_dir, "backend", "train.py")
        lock_file = os.path.join(base_dir, "backend", "training.lock")
        
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)
        
        # Save image and label
        timestamp = int(time.time())
        filename = f"upload_{timestamp}"
        
        image_path = os.path.join(images_dir, f"{filename}.jpg")
        label_path = os.path.join(labels_dir, f"{filename}.txt")
        
        with open(image_path, "wb") as f:
            f.write(image_bytes)
            
        # Convert bounding boxes to YOLO format (class x_center y_center width height normalized)
        with open(label_path, "w") as f:
            for det in detections:
                # YOLO service returns bbox as [x1, y1, x2, y2]
                box = det["bbox"]
                if isinstance(box, list) and len(box) == 4:
                    x1, y1, x2, y2 = box
                    box_width = x2 - x1
                    box_height = y2 - y1
                    x_center = (x1 + box_width / 2.0) / image_width
                    y_center = (y1 + box_height / 2.0) / image_height
                    norm_width = box_width / image_width
                    norm_height = box_height / image_height
                else:
                    # Fallback if somehow it's a dict
                    x_center = (box.get("x", 0) + box.get("width", 0) / 2.0) / image_width
                    y_center = (box.get("y", 0) + box.get("height", 0) / 2.0) / image_height
                    norm_width = box.get("width", 0) / image_width
                    norm_height = box.get("height", 0) / image_height
                
                # Class 0 for egg_tray, Class 1 for hen
                cls_id = 0 if det.get("class") == "egg_tray" else 1
                f.write(f"{cls_id} {x_center:.6f} {y_center:.6f} {norm_width:.6f} {norm_height:.6f}\n")
                
        # Trigger background training if not already running
        if not os.path.exists(lock_file):
            print("Background YOLO training disabled for performance reasons.")
            # subprocess.Popen(["python", train_script], cwd=os.path.join(base_dir, "backend"))
        else:
            print("Training is already running. New image saved for next batch.")
            
    except Exception as e:
        print(f"Failed to process active learning data: {e}")

@router.post("/count-trays")
async def count_trays(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(None),
    file: UploadFile = File(None),
    confidence_threshold: float = Form(0.40),
    target: str = Form("trays"),
    current_user: User = Depends(get_current_user)
):
    """Detect and count only egg trays in an uploaded image and perform active learning."""
    actual_file = image if image else file
    if not actual_file:
        raise HTTPException(status_code=400, detail="No image file provided")
        
    image_bytes = await actual_file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        from app.ai.yolo_service import detect_objects
        # Passing default iou_threshold=0.45 inside the service, or can be added if needed
        result = detect_objects(image_bytes, conf_threshold=confidence_threshold)
        
        # Trigger active learning if trays were found
        if result.get("tray_count", 0) > 0:
            background_tasks.add_task(
                save_to_dataset_and_train, 
                image_bytes, 
                result["detections"]
            )
            
        # Filter detections based on target
        filtered_detections = []
        for det in result.get("detections", []):
            label = det.get("class", "").lower()
            if target == "trays" and "tray" in label:
                filtered_detections.append(det)
            elif target == "hens" and "hen" in label:
                filtered_detections.append(det)
            elif target == "eggs" and "egg" in label and "tray" not in label:
                filtered_detections.append(det)
                
        # Calculate counts
        if target == "trays":
            result["tray_count"] = len(filtered_detections)
            result["egg_count"] = result["tray_count"] * 30
            result["hen_count"] = 0
        elif target == "hens":
            result["hen_count"] = len(filtered_detections)
            result["tray_count"] = 0
            result["egg_count"] = 0
        elif target == "eggs":
            result["egg_count"] = len(filtered_detections)
            result["tray_count"] = 0
            result["hen_count"] = 0
            
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


# ─── OpenAI Vision: Egg & Tray counting ──────────────────────────────────────

# Allowed MIME types for the vision endpoint
_ALLOWED_VISION_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _resolve_content_type(upload: UploadFile) -> str:
    """Return a valid MIME type, falling back to sniffing from the filename extension."""
    from pathlib import Path as _Path
    ct = (upload.content_type or "").lower()
    # Normalise image/jpg -> image/jpeg
    if ct == "image/jpg":
        ct = "image/jpeg"
    if ct in _ALLOWED_VISION_TYPES:
        return ct
    # Fall back to extension-based inference
    suffix = _Path(upload.filename or "").suffix.lower()
    return _EXT_TO_MIME.get(suffix, ct)  # return original if still unknown


@router.post("/analyze-egg-image", tags=["Egg Counting"])
async def analyze_egg_image(
    image: UploadFile = File(..., description="Photo of eggs / egg trays (jpg, jpeg, png, webp)"),
    target: str = Form("trays"),
    current_user: User = Depends(get_current_user),
):
    """
    POST /api/analyze-egg-image

    Analyzes an uploaded photo using OpenAI GPT-4o Vision and returns a
    structured JSON count of eggs and egg trays — separately.

    Returns:
        {
            "success": true,
            "egg_count": 120,
            "tray_count": 10,
            "tray_types": { "green_plastic": 8, "paper_cardboard": 2, "other": 0, "unknown": 0 },
            "confidence": "medium",
            "image_quality": "good",
            "notes": "..."
        }
    """
    from app.config import settings
    from app.schemas.egg_analysis import EggAnalysisResponse

    # ── 1. Validate file presence ────────────────────────────────────────────
    if not image or not image.filename:
        raise HTTPException(status_code=400, detail="No image file provided.")

    # ── 2. Validate MIME type ────────────────────────────────────────────
    content_type = _resolve_content_type(image)
    if content_type not in _ALLOWED_VISION_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported image format: '{content_type}'. "
                "Please upload a JPG, JPEG, PNG, or WEBP image."
            ),
        )

    # ── 3. Read and validate file size ───────────────────────────────────────
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    max_bytes = settings.OPENAI_MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image is too large ({len(image_bytes) // (1024*1024)} MB). "
                f"Maximum allowed size is {settings.OPENAI_MAX_IMAGE_SIZE_MB} MB."
            ),
        )

    # ── 5. Call the Vision detector ──────────────────────────────────
    try:
        from app.ai.detector_interface import get_detector
        detector = get_detector()
        analysis = detector.analyze(image_bytes, content_type, target)
        
        # Override calculation if user selected trays
        if target == "trays" and analysis.get("success"):
            analysis["egg_count"] = analysis.get("tray_count", 0) * 30
            
        return analysis
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unable to process AI response: {exc}",
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        err_msg = str(exc).lower()
        if "rate limit" in err_msg or "quota" in err_msg or "429" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="OpenAI API rate limit reached. Please wait a moment and try again.",
            )
        if any(x in err_msg for x in ["invalid api key", "invalid_api_key", "incorrect api key", "authentication", "401"]):
            raise HTTPException(
                status_code=401,
                detail="Invalid OpenAI API key. Please check your OPENAI_API_KEY setting.",
            )
        raise HTTPException(
            status_code=502,
            detail="Unable to analyze this image. Please upload a clearer photo and try again.",
        )

    # ── 6. Validate and return ───────────────────────────────────────────────
    return EggAnalysisResponse(**analysis)


@router.post("/analyze-dual-egg-images", tags=["Egg Counting"])
async def analyze_dual_egg_images(
    top_image: UploadFile = File(..., description="Top view photo of egg trays"),
    side_image: UploadFile = File(..., description="Side view photo of egg trays"),
    target: str = Form("trays"),
    current_user: User = Depends(get_current_user),
):
    """
    Analyzes two images (Top View and Side View) to calculate total trays.
    """
    from app.config import settings
    from app.schemas.egg_analysis import EggAnalysisResponse

    if not top_image or not top_image.filename or not side_image or not side_image.filename:
        raise HTTPException(status_code=400, detail="Both top and side image files are required.")

    top_content_type = _resolve_content_type(top_image)
    side_content_type = _resolve_content_type(side_image)

    if top_content_type not in _ALLOWED_VISION_TYPES or side_content_type not in _ALLOWED_VISION_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image format. Please upload JPG, PNG, or WEBP."
        )

    top_image_bytes = await top_image.read()
    side_image_bytes = await side_image.read()

    max_bytes = settings.OPENAI_MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(top_image_bytes) > max_bytes or len(side_image_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"One or both images are too large. Max allowed size is {settings.OPENAI_MAX_IMAGE_SIZE_MB} MB."
        )

    try:
        from app.ai.detector_interface import get_detector
        detector = get_detector()
        analysis = detector.analyze_dual(top_image_bytes, side_image_bytes, top_content_type, side_content_type, target)
        
        # Override calculation if user selected trays and model missed it
        if target == "trays" and analysis.get("success"):
            analysis["egg_count"] = analysis.get("tray_count", 0) * 30
            
        return EggAnalysisResponse(**analysis)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unable to process AI response: {exc}")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        err_msg = str(exc).lower()
        if "rate limit" in err_msg or "quota" in err_msg or "429" in err_msg:
            raise HTTPException(status_code=429, detail="API rate limit reached. Please wait a moment.")
        raise HTTPException(status_code=502, detail="Unable to analyze images. Please upload clearer photos.")


@router.post("/chat-analyze", tags=["Egg Counting"])
async def chat_analyze(
    message: str = Form(..., description="User's question or instruction"),
    image: UploadFile = File(None, description="Optional image attachment (jpg, jpeg, png, webp)"),
    current_user: User = Depends(get_current_user),
):
    """
    POST /api/ai/chat-analyze

    Conversational image-analysis assistant. Accepts a text question and an
    optional image. Returns a natural-language reply AND (if image provided)
    a structured analysis result.

    Example:
        message = "How many trays are there?"
        image   = <egg tray photo>

    Returns:
        {
            "reply": "There are approximately 18 visible egg trays.",
            "analysis": { "egg_count": 250, "tray_count": 18, ... }
        }
    """
    from app.config import settings
    from app.schemas.egg_analysis import ChatAnalyzeResponse

    # ── Read image if provided ───────────────────────────────────────────────
    image_bytes: Optional[bytes] = None
    mime_type = "image/jpeg"

    if image and image.filename:
        content_type = _resolve_content_type(image)
        if content_type not in _ALLOWED_VISION_TYPES:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Unsupported image format: '{content_type}'. "
                    "Please upload a JPG, JPEG, PNG, or WEBP image."
                ),
            )

        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Attached image is empty.")

        max_bytes = settings.OPENAI_MAX_IMAGE_SIZE_MB * 1024 * 1024
        if len(image_bytes) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Image is too large. Maximum allowed size is "
                    f"{settings.OPENAI_MAX_IMAGE_SIZE_MB} MB."
                ),
            )
        mime_type = content_type

    # ── Call the Vision detector in chat mode ─────────────────────────
    try:
        from app.ai.detector_interface import get_detector
        detector = get_detector()
        result = detector.chat_analyze(message, image_bytes, mime_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        err_msg = str(exc).lower()
        if "rate limit" in err_msg or "quota" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="OpenAI API rate limit reached. Please wait a moment.",
            )
        raise HTTPException(
            status_code=502,
            detail="Unable to process your request. Please try again.",
        )

    return ChatAnalyzeResponse(
        reply=result["reply"],
        analysis=result.get("analysis"),
    )

@router.post("/thermal-analyze", tags=["Thermal Analysis"])
async def thermal_analyze(
    image: UploadFile = File(..., description="Image or video frame for thermal analysis"),
    min_temp: float = Form(20.0),
    max_temp: float = Form(40.0),
    current_user: User = Depends(get_current_user),
):
    """
    POST /api/ai/thermal-analyze
    Simulates thermal camera detection for hens within a specific temperature range.
    """
    try:
        from fastapi.responses import FileResponse, JSONResponse
        import json
        
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            
        content_type = image.content_type or ""
        is_video = "video" in content_type or image.filename.endswith((".mp4", ".avi", ".mov", ".webm"))
            
        from app.ai.thermal_service import process_thermal_image, process_thermal_video
        
        if is_video:
            result = process_thermal_video(image_bytes, min_temp, max_temp)
            # We return the video file directly, but pass the count in headers
            headers = {
                "X-Hen-Count": str(result["hen_count"]),
                "Access-Control-Expose-Headers": "X-Hen-Count"
            }
            return FileResponse(
                path=result["video_path"], 
                media_type="video/mp4", 
                filename="thermal_output.mp4",
                headers=headers
            )
        else:
            result = process_thermal_image(image_bytes, min_temp, max_temp)
            return result
            
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing thermal media: {str(exc)}")
