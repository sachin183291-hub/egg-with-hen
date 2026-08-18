"""
Audit logging service.
Records all significant actions in the audit_logs table.
Audit records are immutable through normal API.
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from fastapi import Request

from app.database.models import AuditLog, AuditActionEnum


def log_action(
    db: Session,
    action: AuditActionEnum,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    description: Optional[str] = None,
    result: str = "SUCCESS",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    device_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """Create an immutable audit log entry."""

    # Extract request metadata if available
    if request and not ip_address:
        forwarded_for = request.headers.get("X-Forwarded-For")
        ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None

    if request and not user_agent:
        user_agent = request.headers.get("User-Agent", "")[:500]

    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        result=result,
        ip_address=ip_address,
        user_agent=user_agent,
        device_id=device_id,
        extra_data=json.dumps(extra_data) if extra_data else None,
    )
    db.add(entry)
    # Note: caller is responsible for db.commit()
    return entry


def log_and_commit(
    db: Session,
    action: AuditActionEnum,
    **kwargs,
) -> AuditLog:
    """Log an action and immediately commit."""
    entry = log_action(db, action, **kwargs)
    db.commit()
    return entry
