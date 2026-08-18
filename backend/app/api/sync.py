"""Sync API — batch upload from mobile offline queue."""
import json
import uuid
from datetime import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, Device, DeviceStatusEnum, SyncQueue, SyncStatusEnum, AuditActionEnum
from app.schemas.schemas import SyncStatusResponse
from app.security.rbac import get_current_user
from app.services.audit import log_action

router = APIRouter(prefix="/api/sync", tags=["Sync"])


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return sync queue status for the current user's evidence."""
    from app.database.models import Evidence
    user_evidence_ids = [e.id for e in db.query(Evidence.id).filter(Evidence.user_id == current_user.id)]

    q = db.query(SyncQueue).filter(SyncQueue.evidence_id.in_(user_evidence_ids))
    return SyncStatusResponse(
        pending=q.filter(SyncQueue.status == SyncStatusEnum.PENDING).count(),
        uploading=q.filter(SyncQueue.status == SyncStatusEnum.UPLOADING).count(),
        completed=q.filter(SyncQueue.status == SyncStatusEnum.COMPLETED).count(),
        failed=q.filter(SyncQueue.status == SyncStatusEnum.FAILED).count(),
    )


@router.post("/upload")
async def sync_single_upload(
    request: Request,
    file: UploadFile = File(...),
    metadata_json: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Single evidence upload — delegates to evidence API."""
    from app.api.evidence import upload_evidence
    return await upload_evidence(request, file, metadata_json, current_user, db)


@router.post("/batch")
async def batch_sync_status_update(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Acknowledge batch sync completion. Client reports evidence IDs
    that were successfully uploaded so the sync queue can be updated.
    """
    body = await request.json()
    completed_ids = body.get("completed_ids", [])

    updated = 0
    for ev_id in completed_ids:
        sq = db.query(SyncQueue).filter(SyncQueue.evidence_id == ev_id).first()
        if sq:
            sq.status = SyncStatusEnum.COMPLETED
            sq.completed_at = datetime.utcnow()
            updated += 1

    log_action(
        db, AuditActionEnum.SYNC_COMPLETED,
        user_id=current_user.id, resource_type="sync",
        description=f"Batch sync acknowledged: {updated} items", result="SUCCESS", request=request,
    )
    db.commit()
    return {"acknowledged": updated}
