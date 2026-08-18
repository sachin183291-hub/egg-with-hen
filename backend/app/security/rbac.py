"""
Role-Based Access Control (RBAC) dependencies for FastAPI.
Provides get_current_user, require_role, and permission decorators.
"""
from typing import List
# pyrefly: ignore [missing-import]
from fastapi import Depends, HTTPException, status, Request
# pyrefly: ignore [missing-import]
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials 
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, RoleEnum
from app.security.jwt import verify_access_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the current user from the Bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True,
        User.deleted_at == None,
    ).first()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_roles(*roles: RoleEnum):
    """Dependency factory that restricts access to specified roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {[r.value for r in roles]}",
            )
        return current_user
    return role_checker


# Convenience role dependencies
require_super_admin = require_roles(RoleEnum.SUPER_ADMIN)
require_admin_or_above = require_roles(RoleEnum.SUPER_ADMIN, RoleEnum.DEPT_ADMIN)
require_officer_or_above = require_roles(RoleEnum.SUPER_ADMIN, RoleEnum.DEPT_ADMIN, RoleEnum.FIELD_OFFICER)
require_any_authenticated = require_roles(
    RoleEnum.SUPER_ADMIN, RoleEnum.DEPT_ADMIN, RoleEnum.FIELD_OFFICER, RoleEnum.VIEWER
)
