"""Audit logs API — read-only."""
from datetime import datetime
from typing import Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, Query 
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, AuditLog, AuditActionEnum
from app.schemas.schemas import AuditLogResponse, PaginatedResponse
from app.security.rbac import require_admin_or_above

router = APIRouter(prefix="/api/audit-logs", tags=["Audit"])


@router.get("", response_model=PaginatedResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[AuditActionEnum] = Query(None),
    user_id: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())

    if action:
        q = q.filter(AuditLog.action == action)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if result:
        q = q.filter(AuditLog.result == result)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)

    total = q.count()
    logs = q.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
        items=[AuditLogResponse.model_validate(l) for l in logs],
    )
