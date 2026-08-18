"""
SQLAlchemy database models for the GioTag Evidence System.
11 tables covering users, devices, evidence, AI, blockchain, audit.
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
    text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoleEnum(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    DEPT_ADMIN = "DEPT_ADMIN"
    FIELD_OFFICER = "FIELD_OFFICER"
    VIEWER = "VIEWER"


class DeviceStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    REVOKED = "REVOKED"


class EvidenceStatusEnum(str, enum.Enum):
    PENDING_SYNC = "PENDING_SYNC"
    UPLOADED = "UPLOADED"
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"


class AIStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class BlockchainStatusEnum(str, enum.Enum):
    NOT_REGISTERED = "NOT_REGISTERED"
    REGISTERED = "REGISTERED"
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    FAILED = "FAILED"


class SyncStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class AuditActionEnum(str, enum.Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    REGISTER = "REGISTER"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    DEVICE_REGISTERED = "DEVICE_REGISTERED"
    DEVICE_AUTHORIZED = "DEVICE_AUTHORIZED"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    PHOTO_CAPTURED = "PHOTO_CAPTURED"
    PHOTO_UPLOADED = "PHOTO_UPLOADED"
    EVIDENCE_ACCESSED = "EVIDENCE_ACCESSED"
    EVIDENCE_DELETED = "EVIDENCE_DELETED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    AI_VERIFIED = "AI_VERIFIED"
    BLOCKCHAIN_REGISTERED = "BLOCKCHAIN_REGISTERED"
    BLOCKCHAIN_VERIFIED = "BLOCKCHAIN_VERIFIED"
    SYNC_COMPLETED = "SYNC_COMPLETED"
    SYNC_FAILED = "SYNC_FAILED"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"


# ─── Helper ───────────────────────────────────────────────────────────────────

def gen_uuid():
    return str(uuid.uuid4())


# ─── Tables ───────────────────────────────────────────────────────────────────

class Department(Base):
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(200), nullable=False, unique=True)
    code = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users = relationship("User", back_populates="department")

    def __repr__(self):
        return f"<Department {self.code}>"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.FIELD_OFFICER)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    profile_image = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # soft delete

    department = relationship("Department", back_populates="users")
    devices = relationship("Device", back_populates="user", foreign_keys="Device.user_id")
    evidence = relationship("Evidence", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

    __table_args__ = (
        Index("idx_users_email_active", "email", "is_active"),
        Index("idx_users_role", "role"),
    )

    def __repr__(self):
        return f"<User {self.email}>"


class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    device_identifier = Column(String(255), nullable=False, unique=True)
    device_name = Column(String(200), nullable=True)
    device_model = Column(String(200), nullable=True)
    os_type = Column(String(50), nullable=True)
    os_version = Column(String(100), nullable=True)
    app_version = Column(String(50), nullable=True)
    status = Column(Enum(DeviceStatusEnum), default=DeviceStatusEnum.PENDING, nullable=False)
    authorized_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    authorized_at = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    registration_token = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="devices", foreign_keys=[user_id])
    authorizer = relationship("User", foreign_keys=[authorized_by])
    evidence = relationship("Evidence", back_populates="device")

    __table_args__ = (
        Index("idx_devices_user", "user_id"),
        Index("idx_devices_status", "status"),
    )

    def __repr__(self):
        return f"<Device {self.device_identifier}>"


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    evidence_number = Column(String(50), nullable=False, unique=True)  # human-readable ID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False)
    image_filename = Column(String(500), nullable=False)
    image_mime_type = Column(String(100), nullable=False)
    image_size_bytes = Column(Integer, nullable=False)
    image_sha256_hash = Column(String(64), nullable=False, index=True)
    storage_url = Column(String(1000), nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)
    status = Column(Enum(EvidenceStatusEnum), default=EvidenceStatusEnum.PENDING_SYNC, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="evidence")
    device = relationship("Device", back_populates="evidence")
    metadata_ = relationship("EvidenceMetadata", back_populates="evidence", uselist=False, cascade="all, delete-orphan")
    ai_verification = relationship("AIVerification", back_populates="evidence", uselist=False, cascade="all, delete-orphan")
    blockchain_record = relationship("BlockchainRecord", back_populates="evidence", uselist=False, cascade="all, delete-orphan")
    sync_record = relationship("SyncQueue", back_populates="evidence", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_evidence_user", "user_id"),
        Index("idx_evidence_status", "status"),
        Index("idx_evidence_created", "created_at"),
        Index("idx_evidence_hash", "image_sha256_hash"),
    )

    def __repr__(self):
        return f"<Evidence {self.evidence_number}>"


class EvidenceMetadata(Base):
    """GPS, device, and capture details — immutable after creation."""
    __tablename__ = "evidence_metadata"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    evidence_id = Column(String(36), ForeignKey("evidence.id"), nullable=False, unique=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    gps_accuracy_meters = Column(Float, nullable=True)
    altitude_meters = Column(Float, nullable=True)
    capture_timestamp = Column(DateTime(timezone=True), nullable=False)
    timezone = Column(String(100), nullable=True)
    device_identifier = Column(String(255), nullable=True)
    device_model = Column(String(200), nullable=True)
    os_type = Column(String(50), nullable=True)
    os_version = Column(String(100), nullable=True)
    app_version = Column(String(50), nullable=True)
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    evidence = relationship("Evidence", back_populates="metadata_")

    def __repr__(self):
        return f"<EvidenceMetadata evidence={self.evidence_id}>"


class AIVerification(Base):
    __tablename__ = "ai_verification"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    evidence_id = Column(String(36), ForeignKey("evidence.id"), nullable=False, unique=True)
    status = Column(Enum(AIStatusEnum), default=AIStatusEnum.PENDING, nullable=False)
    tamper_probability = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    verification_message = Column(Text, nullable=True)
    ela_score = Column(Float, nullable=True)
    noise_score = Column(Float, nullable=True)
    metadata_consistent = Column(Boolean, nullable=True)
    model_version = Column(String(100), nullable=True, default="opencv-v1.0")
    raw_result = Column(Text, nullable=True)  # JSON string
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    evidence = relationship("Evidence", back_populates="ai_verification")

    def __repr__(self):
        return f"<AIVerification evidence={self.evidence_id} status={self.status}>"


class BlockchainRecord(Base):
    __tablename__ = "blockchain_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    evidence_id = Column(String(36), ForeignKey("evidence.id"), nullable=False, unique=True)
    image_hash = Column(String(64), nullable=False)
    transaction_id = Column(String(255), nullable=True)
    block_number = Column(Integer, nullable=True)
    block_hash = Column(String(255), nullable=True)
    chain_id = Column(String(100), nullable=True)
    provider = Column(String(100), nullable=False, default="local")
    status = Column(Enum(BlockchainStatusEnum), default=BlockchainStatusEnum.NOT_REGISTERED, nullable=False)
    verification_count = Column(Integer, default=0)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    evidence = relationship("Evidence", back_populates="blockchain_record")

    def __repr__(self):
        return f"<BlockchainRecord evidence={self.evidence_id} tx={self.transaction_id}>"


class SyncQueue(Base):
    __tablename__ = "sync_queue"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    evidence_id = Column(String(36), ForeignKey("evidence.id"), nullable=False, unique=True)
    status = Column(Enum(SyncStatusEnum), default=SyncStatusEnum.PENDING, nullable=False)
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    evidence = relationship("Evidence", back_populates="sync_record")

    def __repr__(self):
        return f"<SyncQueue evidence={self.evidence_id} status={self.status}>"


class AuditLog(Base):
    """Immutable audit trail — no update/delete via normal API."""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(Enum(AuditActionEnum), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    ip_address = Column(String(100), nullable=True)
    user_agent = Column(String(500), nullable=True)
    device_id = Column(String(255), nullable=True)
    result = Column(String(50), nullable=True)  # SUCCESS | FAILED | DENIED
    extra_data = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )

    def __repr__(self):
        return f"<AuditLog {self.action} user={self.user_id}>"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default="INFO")  # INFO | WARNING | ERROR | SUCCESS
    is_read = Column(Boolean, default=False)
    related_evidence_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_notifications_user", "user_id"),
        Index("idx_notifications_read", "is_read"),
    )
