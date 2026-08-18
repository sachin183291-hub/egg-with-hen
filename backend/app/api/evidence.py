"""
Evidence API — upload, list, get, delete.
Handles secure multipart upload, hash verification, AI trigger, and blockchain registration.
"""
import uuid
import json
from datetime import datetime
from typing import Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form, UploadFile, File
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


def _generate_evidence_number(db: Session) -> str:
    count = db.query(Evidence).count()
    return f"EV-{datetime.now().year}-{str(count + 1).zfill(5)}"


@router.post("", response_model=EvidenceResponse, status_code=201)
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    metadata_json: str = Form(...),
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
    if server_hash != meta.client_hash:
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

    # Store file
    storage_url = storage.save(content, file.filename or "evidence.jpg")

    # Create evidence record
    ev_id = str(uuid.uuid4())
    evidence = Evidence(
        id=ev_id,
        evidence_number=_generate_evidence_number(db),
        user_id=current_user.id,
        device_id=device.id,
        image_filename=file.filename or "evidence.jpg",
        image_mime_type=file.content_type,
        image_size_bytes=len(content),
        image_sha256_hash=server_hash,
        storage_url=storage_url,
        status=EvidenceStatusEnum.UPLOADED,
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
    device.last_seen = datetime.utcnow()

    log_action(
        db, AuditActionEnum.PHOTO_UPLOADED,
        user_id=current_user.id, resource_type="evidence", resource_id=ev_id,
        description=f"Evidence uploaded: {evidence.evidence_number}", result="SUCCESS",
        request=request, device_id=meta.device_identifier,
    )

    db.commit()
    db.refresh(evidence)

    # Trigger AI verification asynchronously (best-effort)
    try:
        from app.ai.verifier import verify_image_content
        ai_result = verify_image_content(content)
        ai_record = db.query(AIVerification).filter(AIVerification.evidence_id == ev_id).first()
        if ai_record:
            ai_record.status = AIStatusEnum[ai_result["status"]]
            ai_record.tamper_probability = ai_result["tamper_probability"]
            ai_record.confidence_score = ai_result["confidence"]
            ai_record.verification_message = ai_result["message"]
            ai_record.ela_score = ai_result.get("details", {}).get("ela_score")
            ai_record.noise_score = ai_result.get("details", {}).get("noise_score")
            ai_record.metadata_consistent = ai_result.get("details", {}).get("metadata_consistent", True)
            ai_record.verified_at = datetime.utcnow()

            # Update evidence status based on AI
            status_map = {
                "VERIFIED": EvidenceStatusEnum.VERIFIED,
                "SUSPICIOUS": EvidenceStatusEnum.SUSPICIOUS,
                "REVIEW_REQUIRED": EvidenceStatusEnum.REVIEW_REQUIRED,
            }
            evidence.status = status_map.get(ai_result["status"], EvidenceStatusEnum.UPLOADED)
            db.commit()
    except Exception as ai_err:
        # AI failure is non-blocking
        pass

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
