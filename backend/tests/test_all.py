"""
Backend test suite for GioTag Evidence System.
Tests: auth, evidence, devices, AI verification, blockchain, security.
"""
# pyrefly: ignore [missing-import]
import pytest
import json
import io
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient 
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database.session import get_db
from app.database.models import Base

# ─── Test database setup ──────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_giotag.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="session")
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


# ─── Helper: create and login user ────────────────────────────────────────────
def register_and_login(client, email, username, password="Test@1234", role="FIELD_OFFICER"):
    r = client.post("/api/auth/register", json={
        "email": email, "username": username, "full_name": "Test User",
        "password": password, "role": role,
    })
    assert r.status_code in (201, 409), f"Register failed: {r.text}"

    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


# ─── AUTH TESTS ───────────────────────────────────────────────────────────────

class TestAuth:
    def test_register_success(self, client):
        r = client.post("/api/auth/register", json={
            "email": "newuser@test.com",
            "username": "newuser",
            "full_name": "New User",
            "password": "Test@1234",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["email"] == "newuser@test.com"
        assert "hashed_password" not in data

    def test_register_duplicate_email(self, client):
        payload = {"email": "dup@test.com", "username": "dupuser", "full_name": "Dup", "password": "Test@1234"}
        client.post("/api/auth/register", json=payload)
        r = client.post("/api/auth/register", json=payload)
        assert r.status_code == 409

    def test_register_weak_password(self, client):
        r = client.post("/api/auth/register", json={
            "email": "weak@test.com", "username": "weakuser",
            "full_name": "Weak", "password": "short",
        })
        assert r.status_code == 422

    def test_login_success(self, client):
        client.post("/api/auth/register", json={
            "email": "logintest@test.com", "username": "logintest",
            "full_name": "Login Test", "password": "Test@1234",
        })
        r = client.post("/api/auth/login", json={"email": "logintest@test.com", "password": "Test@1234"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        r = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "Wrong@123"})
        assert r.status_code == 401

    def test_me_authenticated(self, client):
        token = register_and_login(client, "me@test.com", "meuser")
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "me@test.com"

    def test_me_unauthenticated(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 403

    def test_refresh_token(self, client):
        client.post("/api/auth/register", json={
            "email": "refresh@test.com", "username": "refreshuser",
            "full_name": "Refresh Test", "password": "Test@1234",
        })
        login_r = client.post("/api/auth/login", json={"email": "refresh@test.com", "password": "Test@1234"})
        refresh_token = login_r.json()["refresh_token"]
        r = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_invalid_jwt(self, client):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401


# ─── ROLE AUTHORIZATION TESTS ─────────────────────────────────────────────────

class TestRBAC:
    def test_viewer_cannot_access_users_list(self, client):
        token = register_and_login(client, "viewer@test.com", "viewertest", role="VIEWER")
        r = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_admin_can_access_users_list(self, client):
        token = register_and_login(client, "admin@test.com", "admintest", role="SUPER_ADMIN")
        r = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_unauthorized_evidence_access(self, client):
        r = client.get("/api/evidence")
        assert r.status_code == 403


# ─── DEVICE TESTS ─────────────────────────────────────────────────────────────

class TestDevices:
    def test_register_device(self, client):
        token = register_and_login(client, "officer.dev@test.com", "officerdev")
        r = client.post("/api/devices/register",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "device_identifier": "ANDROID-TEST-001",
                "device_name": "Test Phone",
                "device_model": "Pixel 8",
                "os_type": "Android",
                "os_version": "14.0",
                "app_version": "1.0.0",
            }
        )
        assert r.status_code == 201
        assert r.json()["device_identifier"] == "ANDROID-TEST-001"
        assert r.json()["status"] == "PENDING"

    def test_register_device_idempotent(self, client):
        token = register_and_login(client, "officer.idem@test.com", "officeridem")
        payload = {"device_identifier": "ANDROID-IDEM-001"}
        r1 = client.post("/api/devices/register",
            headers={"Authorization": f"Bearer {token}"}, json=payload)
        r2 = client.post("/api/devices/register",
            headers={"Authorization": f"Bearer {token}"}, json=payload)
        assert r1.status_code == 201
        assert r2.status_code == 201


# ─── EVIDENCE TESTS ───────────────────────────────────────────────────────────

class TestEvidence:
    def _make_fake_jpeg(self, size_kb: int = 100) -> bytes:
        """Create a minimal valid JPEG bytes for testing."""
        # Minimal JPEG header
        jpeg_header = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
        ])
        # Pad to target size
        padding = b'\x00' * (size_kb * 1024 - len(jpeg_header) - 2)
        jpeg_end = bytes([0xFF, 0xD9])
        return jpeg_header + padding + jpeg_end

    def test_evidence_list_authenticated(self, client):
        token = register_and_login(client, "evlist@test.com", "evlist")
        r = client.get("/api/evidence", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "items" in r.json()

    def test_evidence_not_found(self, client):
        token = register_and_login(client, "evnotfound@test.com", "evnotfound")
        r = client.get("/api/evidence/nonexistent-id", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404


# ─── GPS VALIDATION TESTS ─────────────────────────────────────────────────────

class TestGPSValidation:
    def test_valid_coordinates_accepted(self):
        from app.schemas.schemas import SyncUploadMetadata
        from datetime import datetime
        # Should not raise
        meta = SyncUploadMetadata(
            latitude=40.7128, longitude=-74.0060,
            capture_timestamp=datetime.utcnow(),
            device_identifier="TEST-DEV-001",
            client_hash="a" * 64,
        )
        assert meta.latitude == 40.7128

    def test_hash_mismatch_detection(self, client):
        """Upload with wrong hash should be rejected."""
        token = register_and_login(client, "hashmismatch@test.com", "hashmismatch")
        content = b"fake image content"
        metadata = json.dumps({
            "latitude": 40.7128, "longitude": -74.0060,
            "capture_timestamp": "2024-01-01T12:00:00",
            "device_identifier": "SOME-DEVICE",
            "client_hash": "a" * 64,  # Wrong hash
            "timezone": "UTC",
        })
        r = client.post(
            "/api/evidence",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.jpg", io.BytesIO(content), "image/jpeg")},
            data={"metadata_json": metadata},
        )
        # Either 403 (no authorized device) or 400 (hash mismatch)
        assert r.status_code in (400, 403)


# ─── AI VERIFICATION TESTS ────────────────────────────────────────────────────

class TestAIVerification:
    def test_valid_image_returns_result(self):
        from app.ai.verifier import verify_image_content
        from PIL import Image
        import io

        # Create a valid 100x100 JPEG image
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        content = buf.getvalue()

        result = verify_image_content(content)
        assert result["status"] in ["VERIFIED", "SUSPICIOUS", "REVIEW_REQUIRED"]
        assert 0.0 <= result["tamper_probability"] <= 1.0
        assert 0.0 <= result["confidence"] <= 1.0
        assert "AI-assisted verification" in result["message"]

    def test_invalid_image_handled(self):
        from app.ai.verifier import verify_image_content
        result = verify_image_content(b"not an image at all")
        assert result["status"] in ["VERIFIED", "SUSPICIOUS", "REVIEW_REQUIRED"]

    def test_empty_image_handled(self):
        from app.ai.verifier import verify_image_content
        result = verify_image_content(b"")
        assert result["status"] == "REVIEW_REQUIRED"


# ─── BLOCKCHAIN TESTS ─────────────────────────────────────────────────────────

class TestBlockchain:
    def test_register_and_verify_hash(self):
        from app.blockchain.ledger import LocalTestLedger
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ledger = LocalTestLedger(path)
            evidence_id = "test-ev-001"
            image_hash = "a" * 64

            result = ledger.register_hash(evidence_id, image_hash)
            assert result["evidence_id"] == evidence_id
            assert result["image_hash"] == image_hash
            assert "transaction_id" in result
            assert "block_hash" in result

            verify = ledger.verify_hash(evidence_id, image_hash)
            assert verify["is_valid"] == True
            assert verify["registered_hash"] == image_hash

        finally:
            os.unlink(path)

    def test_hash_mismatch_detected(self):
        from app.blockchain.ledger import LocalTestLedger
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ledger = LocalTestLedger(path)
            ledger.register_hash("test-ev-002", "a" * 64)
            verify = ledger.verify_hash("test-ev-002", "b" * 64)
            assert verify["is_valid"] == False
        finally:
            os.unlink(path)

    def test_unregistered_evidence(self):
        from app.blockchain.ledger import LocalTestLedger
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ledger = LocalTestLedger(path)
            verify = ledger.verify_hash("nonexistent", "a" * 64)
            assert verify["is_valid"] == False
            assert verify["registered"] == False
        finally:
            os.unlink(path)

    def test_blockchain_append_only(self):
        """Chain length should only grow."""
        from app.blockchain.ledger import LocalTestLedger
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ledger = LocalTestLedger(path)
            len1 = ledger.get_chain_length()
            ledger.register_hash("ev-a", "a" * 64)
            len2 = ledger.get_chain_length()
            ledger.register_hash("ev-b", "b" * 64)
            len3 = ledger.get_chain_length()
            assert len1 < len2 < len3
        finally:
            os.unlink(path)


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_endpoint(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_root_endpoint(self, client):
        r = client.get("/")
        assert r.status_code == 200
