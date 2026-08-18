"""Dashboard statistics API."""
from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.session import get_db
from app.database.models import (
    User, Device, Evidence, BlockchainRecord,
    EvidenceStatusEnum, DeviceStatusEnum, BlockchainStatusEnum, RoleEnum
)
from app.schemas.schemas import DashboardStats
from app.security.rbac import require_admin_or_above

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/statistics", response_model=DashboardStats)
async def get_statistics(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    today = datetime.utcnow().date()
    week_ago = datetime.utcnow() - timedelta(days=7)

    ev_q = db.query(Evidence).filter(Evidence.deleted_at == None)

    return DashboardStats(
        total_evidence=ev_q.count(),
        verified_evidence=ev_q.filter(Evidence.status == EvidenceStatusEnum.VERIFIED).count(),
        suspicious_evidence=ev_q.filter(Evidence.status == EvidenceStatusEnum.SUSPICIOUS).count(),
        pending_sync=ev_q.filter(Evidence.status == EvidenceStatusEnum.PENDING_SYNC).count(),
        active_users=db.query(User).filter(User.is_active == True, User.deleted_at == None).count(),
        registered_devices=db.query(Device).count(),
        authorized_devices=db.query(Device).filter(Device.status == DeviceStatusEnum.AUTHORIZED).count(),
        blockchain_records=db.query(BlockchainRecord).filter(
            BlockchainRecord.status == BlockchainStatusEnum.REGISTERED
        ).count(),
        evidence_today=ev_q.filter(func.date(Evidence.created_at) == today).count(),
        evidence_this_week=ev_q.filter(Evidence.created_at >= week_ago).count(),
    )


@router.get("/evidence-trend")
async def get_evidence_trend(
    days: int = 30,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    """Return daily evidence counts for the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(func.date(Evidence.created_at).label("date"), func.count().label("count"))
        .filter(Evidence.created_at >= since, Evidence.deleted_at == None)
        .group_by(func.date(Evidence.created_at))
        .order_by(func.date(Evidence.created_at))
        .all()
    )
    return [{"date": str(r.date), "count": r.count} for r in rows]


@router.get("/status-distribution")
async def get_status_distribution(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    """Return evidence count by status."""
    rows = (
        db.query(Evidence.status, func.count().label("count"))
        .filter(Evidence.deleted_at == None)
        .group_by(Evidence.status)
        .all()
    )
    return [{"status": r.status.value, "count": r.count} for r in rows]


@router.get("/department-stats")
async def get_department_stats(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    """Return evidence count per department."""
    from app.database.models import Department
    rows = (
        db.query(Department.name, Department.code, func.count(Evidence.id).label("count"))
        .join(User, User.department_id == Department.id, isouter=True)
        .join(Evidence, Evidence.user_id == User.id, isouter=True)
        .filter(Evidence.deleted_at == None)
        .group_by(Department.id, Department.name, Department.code)
        .all()
    )
    return [{"name": r.name, "code": r.code, "evidence_count": r.count} for r in rows]
