"""
Pydantic schemas for all API request/response models.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from app.database.models import (
    RoleEnum, DeviceStatusEnum, EvidenceStatusEnum,
    AIStatusEnum, BlockchainStatusEnum, SyncStatusEnum, AuditActionEnum
)

# ─── Base ─────────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: List[Any]

# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    phone: Optional[str] = None
    password: str
    role: RoleEnum = RoleEnum.FIELD_OFFICER
    department_id: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Users ────────────────────────────────────────────────────────────────────

class DepartmentBase(BaseModel):
    id: str
    name: str
    code: str

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    phone: Optional[str]
    role: RoleEnum
    department_id: Optional[str]
    department: Optional[DepartmentBase]
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    phone: Optional[str] = None
    password: str
    role: RoleEnum = RoleEnum.FIELD_OFFICER
    department_id: Optional[str] = None


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[RoleEnum] = None
    department_id: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Devices ──────────────────────────────────────────────────────────────────

class DeviceRegisterRequest(BaseModel):
    device_identifier: str
    device_name: Optional[str] = None
    device_model: Optional[str] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None


class DeviceResponse(BaseModel):
    id: str
    user_id: str
    device_identifier: str
    device_name: Optional[str]
    device_model: Optional[str]
    os_type: Optional[str]
    os_version: Optional[str]
    app_version: Optional[str]
    status: DeviceStatusEnum
    authorized_at: Optional[datetime]
    last_seen: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceStatusUpdateRequest(BaseModel):
    status: DeviceStatusEnum


# ─── Evidence ─────────────────────────────────────────────────────────────────

class EvidenceMetadataResponse(BaseModel):
    id: str
    latitude: float
    longitude: float
    gps_accuracy_meters: Optional[float]
    altitude_meters: Optional[float]
    capture_timestamp: datetime
    timezone: Optional[str]
    device_identifier: Optional[str]
    device_model: Optional[str]
    os_type: Optional[str]
    image_width: Optional[int]
    image_height: Optional[int]

    class Config:
        from_attributes = True


class AIVerificationResponse(BaseModel):
    id: str
    status: AIStatusEnum
    tamper_probability: Optional[float]
    confidence_score: Optional[float]
    verification_message: Optional[str]
    ela_score: Optional[float]
    noise_score: Optional[float]
    metadata_consistent: Optional[bool]
    model_version: Optional[str]
    verified_at: Optional[datetime]

    class Config:
        from_attributes = True


class BlockchainRecordResponse(BaseModel):
    id: str
    image_hash: str
    transaction_id: Optional[str]
    block_number: Optional[int]
    block_hash: Optional[str]
    chain_id: Optional[str]
    provider: str
    status: BlockchainStatusEnum
    registered_at: Optional[datetime]
    last_verified_at: Optional[datetime]

    class Config:
        from_attributes = True


class EvidenceResponse(BaseModel):
    id: str
    evidence_number: str
    user_id: str
    device_id: str
    image_filename: str
    image_mime_type: str
    image_size_bytes: int
    image_sha256_hash: str
    storage_url: Optional[str]
    thumbnail_url: Optional[str]
    status: EvidenceStatusEnum
    rejection_reason: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata_: Optional[EvidenceMetadataResponse] = None
    ai_verification: Optional[AIVerificationResponse] = None
    blockchain_record: Optional[BlockchainRecordResponse] = None
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


class EvidenceUpdateRequest(BaseModel):
    status: Optional[EvidenceStatusEnum] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


# ─── GIS ──────────────────────────────────────────────────────────────────────

class GISMarkerResponse(BaseModel):
    evidence_id: str
    evidence_number: str
    latitude: float
    longitude: float
    status: EvidenceStatusEnum
    capture_timestamp: datetime
    officer_name: str
    ai_status: Optional[AIStatusEnum]
    ai_confidence: Optional[float]
    blockchain_status: Optional[BlockchainStatusEnum]
    thumbnail_url: Optional[str]


# ─── AI ───────────────────────────────────────────────────────────────────────

class AIVerifyRequest(BaseModel):
    evidence_id: str


class AIVerifyResult(BaseModel):
    status: str
    tamper_probability: float
    confidence: float
    message: str
    details: Optional[Dict[str, Any]] = None


# ─── Blockchain ───────────────────────────────────────────────────────────────

class BlockchainRegisterResponse(BaseModel):
    transaction_id: str
    block_number: int
    block_hash: str
    evidence_id: str
    image_hash: str
    registered_at: datetime
    provider: str


class BlockchainVerifyResponse(BaseModel):
    is_valid: bool
    evidence_id: str
    registered_hash: str
    current_hash: str
    transaction_id: Optional[str]
    block_number: Optional[int]
    provider: str
    verified_at: datetime


# ─── Sync ─────────────────────────────────────────────────────────────────────

class SyncUploadMetadata(BaseModel):
    latitude: float
    longitude: float
    gps_accuracy_meters: Optional[float] = None
    altitude_meters: Optional[float] = None
    capture_timestamp: datetime
    timezone: Optional[str] = "UTC"
    device_identifier: str
    device_model: Optional[str] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    client_hash: str  # SHA-256 computed on client side


class SyncStatusResponse(BaseModel):
    pending: int
    uploading: int
    completed: int
    failed: int


# ─── Audit ────────────────────────────────────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str]
    action: AuditActionEnum
    resource_type: Optional[str]
    resource_id: Optional[str]
    description: Optional[str]
    ip_address: Optional[str]
    device_id: Optional[str]
    result: Optional[str]
    created_at: datetime
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_evidence: int
    verified_evidence: int
    suspicious_evidence: int
    pending_sync: int
    active_users: int
    registered_devices: int
    authorized_devices: int
    blockchain_records: int
    evidence_today: int
    evidence_this_week: int


class DepartmentStats(BaseModel):
    name: str
    code: str
    evidence_count: int


# ─── Dept ─────────────────────────────────────────────────────────────────────

class DepartmentResponse(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
