"""Reports API."""
from datetime import datetime, timedelta
from typing import Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.session import get_db
from app.database.models import User, Evidence, AIVerification, EvidenceStatusEnum, AIStatusEnum
from app.security.rbac import require_admin_or_above

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/evidence")
async def evidence_report(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    q = db.query(Evidence).filter(Evidence.deleted_at == None)
    if date_from:
        q = q.filter(Evidence.created_at >= date_from)
    if date_to:
        q = q.filter(Evidence.created_at <= date_to)

    rows = q.all()
    return {
        "total": len(rows),
        "generated_at": datetime.utcnow().isoformat(),
        "date_from": date_from,
        "date_to": date_to,
        "summary": {
            "verified": sum(1 for e in rows if e.status == EvidenceStatusEnum.VERIFIED),
            "suspicious": sum(1 for e in rows if e.status == EvidenceStatusEnum.SUSPICIOUS),
            "pending": sum(1 for e in rows if e.status == EvidenceStatusEnum.PENDING_SYNC),
            "uploaded": sum(1 for e in rows if e.status == EvidenceStatusEnum.UPLOADED),
            "rejected": sum(1 for e in rows if e.status == EvidenceStatusEnum.REJECTED),
        },
    }


@router.get("/suspicious")
async def suspicious_report(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    suspicious = (
        db.query(Evidence, AIVerification)
        .join(AIVerification, AIVerification.evidence_id == Evidence.id, isouter=True)
        .filter(Evidence.status == EvidenceStatusEnum.SUSPICIOUS)
        .filter(Evidence.deleted_at == None)
        .all()
    )

    return {
        "total_suspicious": len(suspicious),
        "generated_at": datetime.utcnow().isoformat(),
        "records": [
            {
                "evidence_id": ev.id,
                "evidence_number": ev.evidence_number,
                "status": ev.status.value,
                "tamper_probability": ai.tamper_probability if ai else None,
                "confidence": ai.confidence_score if ai else None,
                "created_at": ev.created_at.isoformat(),
            }
            for ev, ai in suspicious
        ],
    }


@router.get("/activity")
async def activity_report(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    from app.database.models import AuditLog
    logs = db.query(AuditLog).filter(AuditLog.created_at >= since).count()
    return {
        "total_actions": logs,
        "period_days": days,
        "generated_at": datetime.utcnow().isoformat(),
    }
