"""
GioTag — Secure Geotagged Photo Capture & Monitoring System
FastAPI Backend Application
"""
import os
from pathlib import Path
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse
# pyrefly: ignore [missing-import]
from fastapi import HTTPException

from app.config import settings
from app.database.session import create_tables

# ─── Import all routers ───────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.devices import router as devices_router
from app.api.evidence import router as evidence_router
from app.api.gis import router as gis_router
from app.api.ai import router as ai_router
from app.api.blockchain import router as blockchain_router
from app.api.sync import router as sync_router
from app.api.audit import router as audit_router
from app.api.dashboard import router as dashboard_router
from app.api.reports import router as reports_router
from app.api.tracker import router as tracker_router

# ─── App Factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Secure Geotagged Photo Capture & Monitoring System — "
        "Backend REST API providing JWT auth, evidence management, "
        "AI verification, blockchain hash registration, and GIS data."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# IMPORTANT: Cannot use allow_origin_regex with allow_credentials=True (browser blocks it)
# Set CORS_ORIGINS env var to your actual frontend URL(s) on Render/Vercel
cors_origins = settings.cors_origins_list

# If wildcard "*" is in the list, allow all origins but disable credentials (safe fallback)
if "*" in cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ─── Static file serving for uploads ──────────────────────────────────────────
uploads_path = Path(settings.LOCAL_STORAGE_PATH)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

# ─── Register routers ─────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(devices_router)
app.include_router(evidence_router)
app.include_router(gis_router)
app.include_router(ai_router)
app.include_router(blockchain_router)
app.include_router(sync_router)
app.include_router(audit_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(tracker_router)

# ─── Startup ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Initialize DB tables and seed demo data if configured."""
    create_tables()

    # ALWAYS run super admin health check — ensures login works in hosted environments
    # even after redeploys, DB migrations, or free-tier container restarts.
    try:
        from app.database.seed import ensure_super_admin_active
        ensure_super_admin_active()
    except Exception as e:
        print(f"[WARNING] Super admin health check failed: {e}")

    if settings.SEED_DEMO_DATA:
        try:
            from app.database.seed import seed
            seed()
        except Exception as e:
            print(f"Seed warning: {e}")

    # Initialize blockchain ledger (creates genesis block)
    try:
        from app.blockchain.ledger import blockchain
        print(f"[OK] Blockchain ledger ready ({blockchain.get_chain_length()} blocks)")
    except Exception as e:
        print(f"[WARNING] Blockchain init warning: {e}")

    # Preload AI models to eliminate initial delay and prevent timeout errors
    try:
        from app.ai.yolo_service import load_model
        print("[START] Preloading YOLO models to ensure 5-10s response time...")
        load_model()
        print("[OK] YOLO models preloaded successfully")
    except Exception as e:
        print(f"[WARNING] YOLO model preload failed: {e}")

    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} started ({settings.ENVIRONMENT})")


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "version": settings.APP_VERSION,
    }


# ─── Global error handler ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    
    import traceback
    traceback.print_exc()
    
    if settings.DEBUG:
        return JSONResponse(status_code=500, content={"detail": str(exc), "type": type(exc).__name__})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
