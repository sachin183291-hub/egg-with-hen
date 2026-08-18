"""Users CRUD API with RBAC."""
import uuid
from typing import Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, RoleEnum, AuditActionEnum
from app.schemas.schemas import UserResponse, UserCreateRequest, UserUpdateRequest, PaginatedResponse
from app.security.password import hash_password
from app.security.rbac import get_current_user, require_super_admin, require_admin_or_above

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[RoleEnum] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    q = db.query(User).filter(User.deleted_at == None)
    if search:
        q = q.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%"))
        )
    if role:
        q = q.filter(User.role == role)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)

    # Dept admin can only see their department
    if current_user.role == RoleEnum.DEPT_ADMIN and current_user.department_id:
        q = q.filter(User.department_id == current_user.department_id)

    total = q.count()
    users = q.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
        items=[UserResponse.model_validate(u) for u in users],
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreateRequest,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")

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
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Dept admin can't promote to super admin
    if current_user.role == RoleEnum.DEPT_ADMIN and body.role == RoleEnum.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot assign SUPER_ADMIN role")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    from datetime import datetime
    user.deleted_at = datetime.utcnow()
    user.is_active = False
    db.commit()
