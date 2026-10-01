"""
Authentication module: password hashing via bcrypt, JWT token generation & verification,
and FastAPI dependency for securing endpoints.
"""
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app import db

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int, email: str) -> str:
    """Issue a signed JWT access token for the given user."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRATION_DAYS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    """FastAPI dependency to extract and authenticate the current user from Bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.get("suspended_at"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended, contact support",
        )
    return user


# ---------- Admin Authentication (Cryptographically Separated) ----------

def create_admin_token(email: str) -> str:
    """Issue a signed JWT token for the admin using ADMIN_TOKEN_SECRET."""
    expire = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {
        "sub": "admin",
        "email": email,
        "role": "admin",
        "exp": expire,
    }
    return jwt.encode(payload, settings.ADMIN_TOKEN_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_admin_token(token: str) -> dict:
    """Decode and validate an admin JWT token using ADMIN_TOKEN_SECRET."""
    try:
        payload = jwt.decode(token, settings.ADMIN_TOKEN_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("role") != "admin" or payload.get("sub") != "admin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin authorization role",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_admin(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    """FastAPI dependency to extract and verify admin authorization from Bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_admin_token(credentials.credentials)
    return {
        "email": payload.get("email", settings.ADMIN_EMAIL),
        "role": "admin",
    }

