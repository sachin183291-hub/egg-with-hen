# GioTag — Secure Geotagged Photo Capture & Monitoring System

<div align="center">

![GioTag](https://img.shields.io/badge/GioTag-Evidence%20System-6366f1?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react)
![Flutter](https://img.shields.io/badge/Flutter-Android-02569B?style=for-the-badge&logo=flutter)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql)

</div>

## 🏗️ Architecture Overview

```
giotag project/
├── backend/              ← FastAPI REST API + PostgreSQL/SQLite
│   ├── app/
│   │   ├── api/          ← Auth, Evidence, Users, Devices, GIS, AI, Blockchain, etc.
│   │   ├── ai/           ← ELA + Noise analysis (OpenCV-based, pluggable)
│   │   ├── blockchain/   ← Local test ledger (SHA-256 chain, append-only)
│   │   ├── database/     ← SQLAlchemy models + session management
│   │   ├── schemas/      ← Pydantic validation schemas
│   │   ├── security/     ← JWT, bcrypt, RBAC
│   │   └── services/     ← Storage, audit logging, etc.
│   └── tests/            ← pytest test suite
├── frontend/             ← React 18 + Vite + Leaflet + Recharts dashboard
│   └── src/
│       ├── pages/        ← Dashboard, GIS Map, Evidence, Users, Devices, AI, Blockchain, Audit, Reports, Settings
│       ├── services/     ← Axios API client with JWT interceptor
│       └── hooks/        ← Auth context
└── mobile/               ← Flutter Android app
    └── lib/
        ├── models/       ← Evidence, User models
        ├── screens/      ← Login, Home (camera), Evidence list, Profile
        └── services/     ← API client, SQLite offline DB, Evidence service (GPS+hash+sync)
```

## 🚀 Quick Start

### Option 1 — Docker Compose (Recommended)

```bash
# Copy environment file
cp backend/.env.example backend/.env

# Start everything
docker-compose up --build
```

Services available:
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:5173

---

### Option 2 — Manual Setup

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, etc.

# Run server (uses SQLite by default)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Demo data seeded automatically on first start (see `SEED_DEMO_DATA=true` in .env).

**Demo accounts:**
| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@giotag.gov | Admin@123! |
| Dept Admin | deptadmin@giotag.gov | DeptAdmin@123! |
| Field Officer | officer1@giotag.gov | Officer@123! |
| Viewer | viewer@giotag.gov | Viewer@123! |

#### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Opens at: http://localhost:5173

#### Mobile (Android)

```bash
cd mobile
flutter pub get
flutter run      # Connects to Android emulator
```

> Backend URL: `http://10.0.2.2:8000` (Android emulator → host)

---

## 🔐 Security Architecture

| Component | Implementation |
|-----------|---------------|
| Authentication | JWT (HS256), 30-minute access tokens, 7-day refresh |
| Password Hashing | bcrypt (12 rounds) |
| Authorization | RBAC (4 roles: SUPER_ADMIN, DEPT_ADMIN, FIELD_OFFICER, VIEWER) |
| Image Integrity | SHA-256 hash (client + server verification) |
| Audit Trail | Immutable append-only audit log (all actions logged) |
| Storage | Dual strategy: local filesystem + Supabase adapter |
| Encryption | AES-256 at-rest (configurable) |

## 🤖 AI Verification

The AI pipeline uses **OpenCV-based heuristic analysis** — NOT a trained neural network. This is explicitly labeled:

- **Error Level Analysis (ELA):** Detects JPEG compression inconsistencies indicating potential copy-paste or editing
- **Noise Analysis:** Detects statistical anomalies in pixel noise patterns
- **Combined Score:** Weighted (60% ELA, 40% noise) → VERIFIED / REVIEW_REQUIRED / SUSPICIOUS
- **Extensible:** Swap in a PyTorch model via `AI_MODEL_TYPE=pytorch` (interface defined in `BaseVerifier`)

> ⚠️ The system does NOT claim absolute authenticity. Human review is always recommended for critical decisions.

## ⛓️ Blockchain Layer

The blockchain uses a **local test ledger** (no Ethereum/gas fees needed for demo):

- SHA-256 hash chaining — each block references previous block hash
- Append-only (no delete, no update possible)
- Only stores: `evidence_id + SHA-256 image hash` — NEVER the actual image
- Configurable via `BLOCKCHAIN_MODE=local` (or `ethereum` for future production)

## 📱 Mobile App Features

- **Offline-first:** Camera works without internet; evidence saved locally to SQLite
- **Auto-sync:** When connectivity restored, all pending evidence uploads automatically
- **GPS:** Fine location accuracy with accuracy-threshold alerts
- **SHA-256:** Computed on-device before upload for integrity verification
- **Device Registration:** Each device must be authorized by admin before evidence is accepted

## 🧪 Running Tests

```bash
cd backend
pip install pytest httpx pillow
pytest tests/test_all.py -v
```

## 📋 API Documentation

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | JWT login |
| POST | `/api/auth/register` | User registration |
| GET | `/api/auth/me` | Current user |
| POST | `/api/evidence` | Upload evidence (multipart) |
| GET | `/api/evidence` | List evidence (paginated) |
| GET | `/api/gis/evidence` | GIS markers for map |
| POST | `/api/ai/verify/{id}` | Trigger AI verification |
| POST | `/api/blockchain/register/{id}` | Register hash on blockchain |
| GET | `/api/blockchain/verify/{id}` | Verify blockchain hash |
| GET | `/api/dashboard/statistics` | Dashboard stats |
| GET | `/api/audit-logs` | Audit trail (immutable) |

## 📝 License

MIT License — For development and demonstration purposes only.
