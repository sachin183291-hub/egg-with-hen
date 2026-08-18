"""Devices API — register, list, update status."""
import uuid
from datetime import datetime
from typing import Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, Device, DeviceStatusEnum, AuditActionEnum, RoleEnum
from app.schemas.schemas import DeviceRegisterRequest, DeviceResponse, DeviceStatusUpdateRequest, PaginatedResponse
from app.security.rbac import get_current_user, require_admin_or_above
from app.services.audit import log_action

router = APIRouter(prefix="/api/devices", tags=["Devices"])


@router.post("/register", response_model=DeviceResponse, status_code=201)
async def register_device(
    body: DeviceRegisterRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a new device for the current field officer."""
    existing = db.query(Device).filter(Device.device_identifier == body.device_identifier).first()
    if existing:
        # Return existing record (idempotent)
        return existing

    device = Device(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        device_identifier=body.device_identifier,
        device_name=body.device_name,
        device_model=body.device_model,
        os_type=body.os_type,
        os_version=body.os_version,
        app_version=body.app_version,
        status=DeviceStatusEnum.PENDING,
        last_seen=datetime.utcnow(),
    )
    db.add(device)
    log_action(
        db, AuditActionEnum.DEVICE_REGISTERED,
        user_id=current_user.id, resource_type="device", resource_id=device.id,
        description=f"Device registered: {body.device_identifier}", result="SUCCESS", request=request,
        device_id=body.device_identifier,
    )
    db.commit()
    db.refresh(device)
    return device


@router.get("", response_model=PaginatedResponse)
async def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[DeviceStatusEnum] = Query(None),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    q = db.query(Device)
    if status:
        q = q.filter(Device.status == status)
    if user_id:
        q = q.filter(Device.user_id == user_id)

    total = q.count()
    devices = q.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
        items=[DeviceResponse.model_validate(d) for d in devices],
    )


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Officers can only see their own devices
    if current_user.role == "FIELD_OFFICER" and device.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return device


@router.put("/{device_id}/status", response_model=DeviceResponse)
async def update_device_status(
    device_id: str,
    body: DeviceStatusUpdateRequest,
    request: Request,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.status = body.status
    if body.status == DeviceStatusEnum.AUTHORIZED:
        device.authorized_by = current_user.id
        device.authorized_at = datetime.utcnow()

    action = AuditActionEnum.DEVICE_AUTHORIZED if body.status == DeviceStatusEnum.AUTHORIZED else AuditActionEnum.DEVICE_REVOKED
    log_action(
        db, action,
        user_id=current_user.id, resource_type="device", resource_id=device_id,
        description=f"Device status changed to {body.status.value}", result="SUCCESS", request=request,
    )
    db.commit()
    db.refresh(device)
    return device
