"""
Demo data seeder.
Creates departments, roles, users and sample evidence records for testing.
All demo credentials are clearly labeled.
Run: python -m app.database.seed
"""
import sys
import os
import json
from datetime import datetime, timedelta
import uuid
import hashlib
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.database.session import SessionLocal, create_tables
from app.database.models import (
    Department, User, Device, Evidence, EvidenceMetadata,
    AIVerification, BlockchainRecord, SyncQueue, AuditLog,
    RoleEnum, DeviceStatusEnum, EvidenceStatusEnum,
    AIStatusEnum, BlockchainStatusEnum, SyncStatusEnum, AuditActionEnum
)
from app.security.password import hash_password

# ─── Demo Departments ──────────────────────────────────────────────────────────
DEPARTMENTS = [
    {"name": "Field Operations", "code": "FO", "description": "Primary field operations department"},
    {"name": "Environmental Monitoring", "code": "EM", "description": "Environmental inspection teams"},
    {"name": "Infrastructure Inspection", "code": "II", "description": "Infrastructure assessment teams"},
    {"name": "Administration", "code": "ADMIN", "description": "Administrative staff"},
]

# ─── Demo Users ────────────────────────────────────────────────────────────────
# DEMO CREDENTIALS — NOT FOR PRODUCTION USE
DEMO_USERS = [
    {
        "email": "admin@giotag.gov",
        "username": "superadmin",
        "full_name": "System Administrator",
        "phone": "+1-555-0100",
        "password": "Admin@123!",
        "role": RoleEnum.SUPER_ADMIN,
        "dept_code": "ADMIN",
        "is_verified": True,
    },
    {
        "email": "deptadmin@giotag.gov",
        "username": "deptadmin",
        "full_name": "Department Admin",
        "phone": "+1-555-0101",
        "password": "DeptAdmin@123!",
        "role": RoleEnum.DEPT_ADMIN,
        "dept_code": "FO",
        "is_verified": True,
    },
    {
        "email": "officer1@giotag.gov",
        "username": "officer_john",
        "full_name": "John Field Officer",
        "phone": "+1-555-0102",
        "password": "Officer@123!",
        "role": RoleEnum.FIELD_OFFICER,
        "dept_code": "FO",
        "is_verified": True,
    },
    {
        "email": "officer2@giotag.gov",
        "username": "officer_jane",
        "full_name": "Jane Inspector",
        "phone": "+1-555-0103",
        "password": "Officer@123!",
        "role": RoleEnum.FIELD_OFFICER,
        "dept_code": "EM",
        "is_verified": True,
    },
    {
        "email": "viewer@giotag.gov",
        "username": "viewer_bob",
        "full_name": "Bob Viewer",
        "phone": "+1-555-0104",
        "password": "Viewer@123!",
        "role": RoleEnum.VIEWER,
        "dept_code": "ADMIN",
        "is_verified": True,
    },
]

# Sample GPS coordinates (various locations for demo)
SAMPLE_LOCATIONS = [
    (40.7128, -74.0060),   # New York
    (34.0522, -118.2437),  # Los Angeles
    (41.8781, -87.6298),   # Chicago
    (29.7604, -95.3698),   # Houston
    (33.4484, -112.0740),  # Phoenix
    (39.9526, -75.1652),   # Philadelphia
    (29.4241, -98.4936),   # San Antonio
    (32.7767, -96.7970),   # Dallas
    (30.3322, -81.6557),   # Jacksonville
    (30.2672, -97.7431),   # Austin
]


def generate_evidence_number(index: int) -> str:
    return f"EV-{datetime.now().year}-{str(index).zfill(5)}"


def fake_image_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def seed():
    print("[START] Starting demo data seed...")
    create_tables()
    db = SessionLocal()

    try:
        # Check if already seeded
        existing = db.query(User).filter(User.email == "admin@giotag.gov").first()
        if existing:
            print("[OK] Demo data already exists. Skipping seed.")
            return

        # ── Departments ──────────────────────────────────────────
        dept_map = {}
        for d in DEPARTMENTS:
            dept = Department(id=str(uuid.uuid4()), **d)
            db.add(dept)
            dept_map[d["code"]] = dept
        db.flush()
        print(f"  [OK] Created {len(DEPARTMENTS)} departments")

        # ── Users ────────────────────────────────────────────────
        user_map = {}
        for u in DEMO_USERS:
            dept_code = u.pop("dept_code")
            password = u.pop("password")
            user = User(
                id=str(uuid.uuid4()),
                hashed_password=hash_password(password),
                department_id=dept_map[dept_code].id,
                **u,
            )
            db.add(user)
            user_map[user.email] = user
        db.flush()
        print(f"  [OK] Created {len(DEMO_USERS)} demo users")

        # ── Devices ──────────────────────────────────────────────
        officer1 = user_map["officer1@giotag.gov"]
        officer2 = user_map["officer2@giotag.gov"]
        admin = user_map["admin@giotag.gov"]

        devices = []
        device_data = [
            {
                "user": officer1,
                "device_identifier": "DEMO-DEVICE-001-ANDROID",
                "device_name": "Officer John Phone",
                "device_model": "Samsung Galaxy S23",
                "os_type": "Android",
                "os_version": "14.0",
                "app_version": "1.0.0",
                "status": DeviceStatusEnum.AUTHORIZED,
            },
            {
                "user": officer2,
                "device_identifier": "DEMO-DEVICE-002-ANDROID",
                "device_name": "Officer Jane Phone",
                "device_model": "Google Pixel 8",
                "os_type": "Android",
                "os_version": "14.0",
                "app_version": "1.0.0",
                "status": DeviceStatusEnum.AUTHORIZED,
            },
            {
                "user": officer1,
                "device_identifier": "DEMO-DEVICE-003-PENDING",
                "device_name": "John Backup Device",
                "device_model": "OnePlus 11",
                "os_type": "Android",
                "os_version": "13.0",
                "app_version": "1.0.0",
                "status": DeviceStatusEnum.PENDING,
            },
        ]

        for dd in device_data:
            user_obj = dd.pop("user")
            dev = Device(
                id=str(uuid.uuid4()),
                user_id=user_obj.id,
                authorized_by=admin.id if dd["status"] == DeviceStatusEnum.AUTHORIZED else None,
                authorized_at=datetime.utcnow() if dd["status"] == DeviceStatusEnum.AUTHORIZED else None,
                **dd,
            )
            db.add(dev)
            devices.append(dev)
        db.flush()
        print(f"  [OK] Created {len(devices)} demo devices")

        # ── Evidence ──────────────────────────────────────────────
        authorized_device = devices[0]
        evidence_list = []
        statuses = [
            EvidenceStatusEnum.VERIFIED,
            EvidenceStatusEnum.VERIFIED,
            EvidenceStatusEnum.SUSPICIOUS,
            EvidenceStatusEnum.UPLOADED,
            EvidenceStatusEnum.VERIFIED,
            EvidenceStatusEnum.REVIEW_REQUIRED,
            EvidenceStatusEnum.VERIFIED,
            EvidenceStatusEnum.REJECTED,
            EvidenceStatusEnum.UPLOADED,
            EvidenceStatusEnum.VERIFIED,
        ]

        for i, (lat, lon) in enumerate(SAMPLE_LOCATIONS):
            ev_id = str(uuid.uuid4())
            img_hash = fake_image_hash(f"demo-evidence-{i}-{ev_id}")
            capture_time = datetime.utcnow() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
            status = statuses[i]

            ev = Evidence(
                id=ev_id,
                evidence_number=generate_evidence_number(i + 1),
                user_id=officer1.id if i % 2 == 0 else officer2.id,
                device_id=authorized_device.id,
                image_filename=f"evidence_{i+1:04d}.jpg",
                image_mime_type="image/jpeg",
                image_size_bytes=random.randint(500_000, 5_000_000),
                image_sha256_hash=img_hash,
                storage_url=f"/uploads/demo/evidence_{i+1:04d}.jpg",
                status=status,
                notes=f"Demo evidence capture #{i+1}",
                created_at=capture_time,
            )
            db.add(ev)
            evidence_list.append(ev)

            # Metadata
            meta = EvidenceMetadata(
                id=str(uuid.uuid4()),
                evidence_id=ev_id,
                latitude=lat + random.uniform(-0.01, 0.01),
                longitude=lon + random.uniform(-0.01, 0.01),
                gps_accuracy_meters=random.uniform(3.0, 15.0),
                altitude_meters=random.uniform(0, 100),
                capture_timestamp=capture_time,
                timezone="UTC",
                device_identifier=authorized_device.device_identifier,
                device_model=authorized_device.device_model,
                os_type="Android",
                os_version="14.0",
                app_version="1.0.0",
                image_width=4032,
                image_height=3024,
            )
            db.add(meta)

            # AI Verification
            ai_status_map = {
                EvidenceStatusEnum.VERIFIED: AIStatusEnum.VERIFIED,
                EvidenceStatusEnum.SUSPICIOUS: AIStatusEnum.SUSPICIOUS,
                EvidenceStatusEnum.REVIEW_REQUIRED: AIStatusEnum.REVIEW_REQUIRED,
                EvidenceStatusEnum.UPLOADED: AIStatusEnum.PENDING,
                EvidenceStatusEnum.REJECTED: AIStatusEnum.SUSPICIOUS,
            }
            ai_status = ai_status_map.get(status, AIStatusEnum.PENDING)
            tamper_prob = 0.05 if ai_status == AIStatusEnum.VERIFIED else (0.72 if ai_status == AIStatusEnum.SUSPICIOUS else 0.35)
            conf = 0.92 if ai_status == AIStatusEnum.VERIFIED else (0.85 if ai_status == AIStatusEnum.SUSPICIOUS else 0.65)

            ai = AIVerification(
                id=str(uuid.uuid4()),
                evidence_id=ev_id,
                status=ai_status,
                tamper_probability=tamper_prob,
                confidence_score=conf,
                verification_message="AI-assisted verification result. " + (
                    "No significant anomalies detected." if ai_status == AIStatusEnum.VERIFIED
                    else "Potential manipulation detected. Manual review recommended."
                    if ai_status == AIStatusEnum.SUSPICIOUS
                    else "Inconclusive analysis. Human review required."
                ),
                ela_score=random.uniform(0.02, 0.15) if ai_status == AIStatusEnum.VERIFIED else random.uniform(0.4, 0.8),
                noise_score=random.uniform(0.05, 0.2) if ai_status == AIStatusEnum.VERIFIED else random.uniform(0.3, 0.7),
                metadata_consistent=ai_status == AIStatusEnum.VERIFIED,
                model_version="opencv-v1.0",
                verified_at=capture_time + timedelta(seconds=30) if ai_status != AIStatusEnum.PENDING else None,
            )
            db.add(ai)

            # Blockchain
            if status in [EvidenceStatusEnum.VERIFIED, EvidenceStatusEnum.SUSPICIOUS]:
                bc_tx_id = hashlib.sha256(f"tx-{ev_id}".encode()).hexdigest()[:16]
                bc = BlockchainRecord(
                    id=str(uuid.uuid4()),
                    evidence_id=ev_id,
                    image_hash=img_hash,
                    transaction_id=f"0x{bc_tx_id}",
                    block_number=random.randint(1000, 9999),
                    block_hash=hashlib.sha256(f"block-{ev_id}".encode()).hexdigest(),
                    chain_id="local-testnet",
                    provider="local",
                    status=BlockchainStatusEnum.REGISTERED,
                    registered_at=capture_time + timedelta(minutes=2),
                )
                db.add(bc)

        db.flush()
        print(f"  [OK] Created {len(evidence_list)} demo evidence records")

        # ── Audit Logs ───────────────────────────────────────────
        audit_actions = [
            AuditLog(
                id=str(uuid.uuid4()),
                user_id=admin.id,
                action=AuditActionEnum.LOGIN,
                resource_type="auth",
                resource_id=admin.id,
                description="Super admin login",
                ip_address="192.168.1.100",
                result="SUCCESS",
                created_at=datetime.utcnow() - timedelta(hours=2),
            ),
            AuditLog(
                id=str(uuid.uuid4()),
                user_id=officer1.id,
                action=AuditActionEnum.PHOTO_CAPTURED,
                resource_type="evidence",
                resource_id=evidence_list[0].id,
                description=f"Photo captured: {evidence_list[0].evidence_number}",
                ip_address="10.0.0.50",
                device_id=authorized_device.device_identifier,
                result="SUCCESS",
                created_at=datetime.utcnow() - timedelta(hours=1),
            ),
            AuditLog(
                id=str(uuid.uuid4()),
                user_id=officer1.id,
                action=AuditActionEnum.BLOCKCHAIN_REGISTERED,
                resource_type="blockchain",
                resource_id=evidence_list[0].id,
                description="Hash registered on blockchain",
                result="SUCCESS",
                created_at=datetime.utcnow() - timedelta(minutes=55),
            ),
        ]
        for al in audit_actions:
            db.add(al)

        db.commit()
        print("[OK] Demo data seed completed successfully!")
        print("\n[INFO] DEMO CREDENTIALS (for testing only):")
        print("  Super Admin:    admin@giotag.gov       / Admin@123!")
        print("  Dept Admin:     deptadmin@giotag.gov   / DeptAdmin@123!")
        print("  Field Officer:  officer1@giotag.gov    / Officer@123!")
        print("  Viewer:         viewer@giotag.gov      / Viewer@123!")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
