"""Auth API — register, login, refresh, logout, /me"""
from datetime import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, status, Request 
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, RoleEnum, AuditActionEnum
from app.schemas.schemas import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserResponse
from app.security.password import hash_password, verify_password
from app.security.jwt import create_access_token, create_refresh_token, verify_refresh_token
from app.security.rbac import get_current_user
from app.services.audit import log_action
from app.config import settings
import uuid

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Register a new user account. Role defaults to FIELD_OFFICER."""
    # Check duplicate email
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        username=body.username,
        full_name=body.full_name,
        phone=body.phone,
        hashed_password=hash_password(body.password),
        role=body.role,
        department_id=body.department_id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    log_action(
        db, AuditActionEnum.REGISTER,
        user_id=user.id, resource_type="user", resource_id=user.id,
        description=f"New user registered: {user.email}", result="SUCCESS", request=request,
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate user and return JWT tokens."""
    user = db.query(User).filter(
        User.email == body.email,
        User.deleted_at == None,
    ).first()

    if not user or not verify_password(body.password, user.hashed_password):
        log_action(
            db, AuditActionEnum.LOGIN,
            description=f"Failed login attempt for: {body.email}",
            result="FAILED", request=request,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login = datetime.utcnow()
    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})

    log_action(
        db, AuditActionEnum.LOGIN,
        user_id=user.id, resource_type="auth", resource_id=user.id,
        description=f"User login: {user.email}", result="SUCCESS", request=request,
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Use a refresh token to obtain a new access token."""
    payload = verify_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    new_refresh = create_refresh_token({"sub": user.id})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.post("/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logout — client should discard tokens. Log the event."""
    log_action(
        db, AuditActionEnum.LOGOUT,
        user_id=current_user.id, resource_type="auth", resource_id=current_user.id,
        description=f"User logout: {current_user.email}", result="SUCCESS", request=request,
    )
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user
