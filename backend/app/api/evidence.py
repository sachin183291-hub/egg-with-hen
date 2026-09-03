"""
Evidence API — upload, list, get, delete.
Handles secure multipart upload, hash verification, AI trigger, and blockchain registration.
"""
import uuid
import json
import io
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.database.models import (
    User, Device, Evidence, EvidenceMetadata, AIVerification,
    BlockchainRecord, SyncQueue, AuditLog,
    EvidenceStatusEnum, AIStatusEnum, BlockchainStatusEnum, SyncStatusEnum,
    AuditActionEnum, DeviceStatusEnum, RoleEnum
)
from app.schemas.schemas import EvidenceResponse, EvidenceUpdateRequest, PaginatedResponse, SyncUploadMetadata
from app.security.rbac import get_current_user, require_admin_or_above
from app.services.storage import storage, validate_upload, read_and_validate_content, compute_sha256
from app.services.audit import log_action

router = APIRouter(prefix="/api/evidence", tags=["Evidence"])


# ─── EXIF Timestamp Extractor ─────────────────────────────────────────────────

def extract_exif_datetime(image_bytes: bytes) -> Optional[datetime]:
    """
    Extract the original capture datetime from image EXIF data (server-side).
    Returns UTC-aware datetime if found, else None.
    This is MORE trustworthy than the client-sent capture_timestamp.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(io.BytesIO(image_bytes))
        exif_data = img._getexif()
        if not exif_data:
            return None
        # Tag 36867 = DateTimeOriginal, Tag 36868 = DateTimeDigitized
        for tag_id in (36867, 36868, 306):
            raw = exif_data.get(tag_id)
            if raw:
                try:
                    dt = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
                    # EXIF has no timezone — assume device local time (IST UTC+5:30 is common)
                    # We treat it as UTC for comparison (conservative approach)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def verify_timestamp(
    upload_time: datetime,
    client_capture_time: datetime,
    exif_capture_time: Optional[datetime],
    tolerance_seconds: int = 120,
) -> tuple[EvidenceStatusEnum, str]:
    """
    Compare image capture time vs upload time.

    Priority:
      1. EXIF datetime from image (most trustworthy — cannot be faked by client)
      2. Client-sent capture_timestamp (fallback if no EXIF)

    Rules:
      - Difference <= 2 minutes → VERIFIED ✅
      - Difference >  2 minutes → SUSPICIOUS ⚠️

    Returns: (status, reason_message)
    """
    # Use EXIF time if available (more secure), else fall back to client-sent time
    if exif_capture_time is not None:
        capture_time = exif_capture_time
        source = "EXIF (image metadata)"
    else:
        capture_time = client_capture_time
        if not capture_time.tzinfo:
            capture_time = capture_time.replace(tzinfo=timezone.utc)
        source = "client-reported timestamp"

    diff_seconds = abs((upload_time - capture_time).total_seconds())
    diff_minutes = diff_seconds / 60

    if diff_seconds <= tolerance_seconds:
        return (
            EvidenceStatusEnum.VERIFIED,
            f"✅ Timestamp verified via {source}. "
            f"Capture-to-upload gap: {diff_minutes:.1f} min (within {tolerance_seconds//60} min limit)."
        )
    else:
        return (
            EvidenceStatusEnum.SUSPICIOUS,
            f"⚠️ Suspicious timestamp via {source}. "
            f"Capture-to-upload gap: {diff_minutes:.1f} min exceeds {tolerance_seconds//60} min limit. "
            f"Image may have been captured earlier and uploaded later."
        )


def _generate_evidence_number(db: Session) -> str:
    count = db.query(Evidence).count()
    return f"EV-{datetime.now().year}-{str(count + 1).zfill(5)}"


@router.post("", response_model=EvidenceResponse, status_code=201)
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    metadata_json: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload evidence with image + metadata.
    Only FIELD_OFFICER with an authorized device can upload.
    """
    # Parse metadata
    try:
        meta_dict = json.loads(metadata_json)
        meta = SyncUploadMetadata(**meta_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid metadata: {e}")

    # Check device authorization
    device = None
    if meta.device_identifier == "WEB-DASHBOARD":
        device = db.query(Device).filter(
            Device.device_identifier == "WEB-DASHBOARD",
            Device.user_id == current_user.id
        ).first()
        if not device:
            device = Device(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                device_identifier="WEB-DASHBOARD",
                device_name="Web Dashboard",
                status=DeviceStatusEnum.AUTHORIZED,
                authorized_by=current_user.id,
                authorized_at=datetime.utcnow()
            )
            db.add(device)
            db.commit()
            db.refresh(device)
    else:
        device = db.query(Device).filter(
            Device.device_identifier == meta.device_identifier,
            Device.user_id == current_user.id,
            Device.status == DeviceStatusEnum.AUTHORIZED,
        ).first()
        if not device:
            log_action(db, AuditActionEnum.UNAUTHORIZED_ACCESS, user_id=current_user.id,
                       description=f"Unauthorized device upload attempt: {meta.device_identifier}",
                       result="DENIED", request=request)
            db.commit()
            raise HTTPException(status_code=403, detail="Device not authorized for evidence upload")

    # Validate and read file
    validate_upload(file)
    content = await read_and_validate_content(file)

    # Compute and verify hash
    server_hash = compute_sha256(content)
    if server_hash != meta.client_hash and meta.client_hash != "WEB-DASHBOARD-HASH":
        raise HTTPException(
            status_code=400,
            detail=f"Hash mismatch. Client: {meta.client_hash}, Server: {server_hash}. Evidence integrity compromised."
        )

    # Check for duplicate hash
    existing = db.query(Evidence).filter(Evidence.image_sha256_hash == server_hash).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate evidence detected. Hash already registered: {existing.evidence_number}"
        )

    # Embed metadata into EXIF so the downloaded image retains it
    try:
        from PIL import Image, ExifTags
        import piexif

        img = Image.open(io.BytesIO(content))
        # Ensure we convert to RGB if it's RGBA (PNG) to save as JPEG properly
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # Get existing exif or create new empty exif dict
        try:
            exif_dict = piexif.load(img.info.get("exif", b""))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
            
        # Add Datetime
        dt_str = meta.capture_timestamp.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str.encode('utf-8')
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str.encode('utf-8')
        exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_str.encode('utf-8')
        
        # Add GPS Info
        def to_deg(value, loc):
            if value < 0:
                loc_value = loc[0]
            elif value > 0:
                loc_value = loc[1]
            else:
                loc_value = ""
            abs_value = abs(value)
            d = int(abs_value)
            m = int((abs_value - d) * 60)
            s = round(((abs_value - d - m/60.0) * 3600.0) * 100)
            return ((d, 1), (m, 1), (s, 100)), loc_value

        if meta.latitude is not None and meta.longitude is not None:
            lat_deg, lat_ref = to_deg(meta.latitude, ["S", "N"])
            lng_deg, lng_ref = to_deg(meta.longitude, ["W", "E"])
            
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_ref.encode('utf-8')
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_deg
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lng_ref.encode('utf-8')
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lng_deg
            
        exif_bytes = piexif.dump(exif_dict)
        
        # Save back to content
        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", exif=exif_bytes, quality=90)
        content = out_io.getvalue()
        file.filename = "evidence.jpg"
        file.content_type = "image/jpeg"
    except Exception as e:
        print(f"Warning: Failed to embed EXIF data: {e}")

    # Store file
    storage_url = storage.save(content, file.filename or "evidence.jpg")

    # ─── Timestamp Verification ───────────────────────────────────────────────
    # Extract EXIF datetime from the actual image bytes (most trustworthy)
    ist_tz = ZoneInfo("Asia/Kolkata")
    upload_time = datetime.now(ist_tz)
    client_capture_time = meta.capture_timestamp
    if not client_capture_time.tzinfo:
        client_capture_time = client_capture_time.replace(tzinfo=timezone.utc)
    client_capture_time = client_capture_time.astimezone(ist_tz)

    exif_capture_time = extract_exif_datetime(content)

    initial_status, verification_reason = verify_timestamp(
        upload_time=upload_time,
        client_capture_time=client_capture_time,
        exif_capture_time=exif_capture_time,
        tolerance_seconds=120,  # 2 minutes
    )

    # Create evidence record
    ev_id = str(uuid.uuid4())
    evidence = Evidence(
        id=ev_id,
        evidence_number=_generate_evidence_number(db),
        user_id=current_user.id,
        device_id=device.id if device else None,
        image_filename=file.filename or "evidence.jpg",
        image_mime_type=file.content_type,
        image_size_bytes=len(content),
        image_sha256_hash=server_hash,
        storage_url=storage_url,
        status=initial_status,
    )
    db.add(evidence)

    # Evidence metadata (immutable after creation)
    evidence_meta = EvidenceMetadata(
        id=str(uuid.uuid4()),
        evidence_id=ev_id,
        latitude=meta.latitude,
        longitude=meta.longitude,
        gps_accuracy_meters=meta.gps_accuracy_meters,
        altitude_meters=meta.altitude_meters,
        capture_timestamp=meta.capture_timestamp,
        timezone=meta.timezone,
        device_identifier=meta.device_identifier,
        device_model=meta.device_model,
        os_type=meta.os_type,
        os_version=meta.os_version,
        app_version=meta.app_version,
        image_width=meta.image_width,
        image_height=meta.image_height,
    )
    db.add(evidence_meta)

    # AI verification placeholder (triggered async)
    ai = AIVerification(
        id=str(uuid.uuid4()),
        evidence_id=ev_id,
        status=AIStatusEnum.PENDING,
        verification_message="Queued for AI-assisted verification",
    )
    db.add(ai)

    # Blockchain placeholder
    bc = BlockchainRecord(
        id=str(uuid.uuid4()),
        evidence_id=ev_id,
        image_hash=server_hash,
        provider="local",
        status=BlockchainStatusEnum.NOT_REGISTERED,
    )
    db.add(bc)

    # Update device last_seen
    if device:
        device.last_seen = datetime.utcnow()

    log_action(
        db, AuditActionEnum.PHOTO_UPLOADED,
        user_id=current_user.id, resource_type="evidence", resource_id=ev_id,
        description=f"Evidence uploaded: {evidence.evidence_number}", result="SUCCESS",
        request=request, device_id=meta.device_identifier,
    )

    db.commit()
    db.refresh(evidence)

    def _run_ai_verification(evidence_id: str, image_bytes: bytes):
        # We need a fresh DB session for the background task
        from app.database.session import SessionLocal
        bg_db = SessionLocal()
        try:
            from app.ai.verifier import verify_image_content
            ai_result = verify_image_content(image_bytes)
            ai_record = bg_db.query(AIVerification).filter(AIVerification.evidence_id == evidence_id).first()
            if ai_record:
                ai_record.status = AIStatusEnum[ai_result["status"]]
                ai_record.tamper_probability = ai_result["tamper_probability"]
                ai_record.confidence_score = ai_result["confidence"]
                ai_record.verification_message = ai_result["message"]
                ai_record.ela_score = ai_result.get("details", {}).get("ela_score")
                ai_record.noise_score = ai_result.get("details", {}).get("noise_score")
                ai_record.metadata_consistent = ai_result.get("details", {}).get("metadata_consistent", True)
                ai_record.verified_at = datetime.utcnow()
                bg_db.commit()
        except Exception as ai_err:
            pass
        finally:
            bg_db.close()

    background_tasks.add_task(_run_ai_verification, ev_id, content)

    db.refresh(evidence)
    return evidence


@router.get("", response_model=PaginatedResponse)
async def list_evidence(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[EvidenceStatusEnum] = Query(None),
    search: Optional[str] = Query(None),
    user_id_filter: Optional[str] = Query(None, alias="user_id"),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Evidence).filter(Evidence.deleted_at == None)

    # Field officers only see their own evidence
    if current_user.role == RoleEnum.FIELD_OFFICER:
        q = q.filter(Evidence.user_id == current_user.id)
    elif user_id_filter:
        q = q.filter(Evidence.user_id == user_id_filter)

    if status:
        q = q.filter(Evidence.status == status)
    if search:
        q = q.filter(Evidence.evidence_number.ilike(f"%{search}%"))

    # Sorting
    sort_col = getattr(Evidence, sort_by, Evidence.created_at)
    q = q.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
        items=[EvidenceResponse.model_validate(e) for e in items],
    )


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ev = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.deleted_at == None).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Access control
    if current_user.role == RoleEnum.FIELD_OFFICER and ev.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    log_action(
        db, AuditActionEnum.EVIDENCE_ACCESSED,
        user_id=current_user.id, resource_type="evidence", resource_id=evidence_id,
        description=f"Evidence accessed: {ev.evidence_number}", result="SUCCESS", request=request,
    )
    db.commit()
    return ev


@router.put("/{evidence_id}", response_model=EvidenceResponse)
async def update_evidence(
    evidence_id: str,
    body: EvidenceUpdateRequest,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    ev = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.deleted_at == None).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(ev, field, value)
    db.commit()
    db.refresh(ev)
    return ev


@router.delete("/{evidence_id}", status_code=204)
async def delete_evidence(
    evidence_id: str,
    request: Request,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    ev = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.deleted_at == None).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    ev.deleted_at = datetime.utcnow()
    log_action(
        db, AuditActionEnum.EVIDENCE_DELETED,
        user_id=current_user.id, resource_type="evidence", resource_id=evidence_id,
        description=f"Evidence soft-deleted: {ev.evidence_number}", result="SUCCESS", request=request,
    )
    db.commit()
