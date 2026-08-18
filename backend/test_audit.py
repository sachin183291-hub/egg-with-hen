import asyncio
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
# pyrefly: ignore [missing-import]
from fastapi import FastAPI
from app.api.audit import router
from app.database.session import Base, engine, SessionLocal
from app.security.rbac import require_admin_or_above
from app.database.models import User, RoleEnum, AuditLog, AuditActionEnum

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(router)

def override_require_admin_or_above():
    return User(id="test_user", email="test@example.com", role=RoleEnum.SUPER_ADMIN)

app.dependency_overrides[require_admin_or_above] = override_require_admin_or_above

# Insert test data
db = SessionLocal()
if db.query(AuditLog).count() == 0:
    al = AuditLog(action=AuditActionEnum.LOGIN)
    db.add(al)
    db.commit()
db.close()

client = TestClient(app)

response = client.get("/api/audit-logs")
print("STATUS:", response.status_code)
print("BODY:", response.json())
