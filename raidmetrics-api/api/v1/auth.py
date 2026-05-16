import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Depends, HTTPException, Response
from fastapi.security import HTTPBearer
from jose import JWTError, jwt

from ..dal.db import get_db
from ..dal.models import User

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRES_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRES_MINUTES", "1440"))
REFRESH_TOKEN_EXPIRES_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "30"))

def create_access_token(user_id: int):
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
    payload = {
        "sub": str(user_id),
        # Use integer seconds for better cross-lang compatibility (Rust expects i64)
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, exp


def generate_refresh_token():
    # produce a secure random token string (we'll hash before storing)
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    # use SHA-256 (not PBKDF — token is already random; you may use bcrypt if preferred)
    return hashlib.sha256(token.encode()).hexdigest()


def verify_hashed(token: str, token_hash: str) -> bool:
    return hash_token(token) == token_hash


# cookie helpers
def set_refresh_cookie(response: Response, refresh_token: str, max_age: int):
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Strict",
        max_age=max_age,
        path="/api/v1/auth",
    )


def clear_refresh_cookie(response: Response):
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    )


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid access token")


def verify_access_token(credentials=Depends(HTTPBearer())):
    try:
        token = credentials.credentials
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid access token")


def get_current_user(credentials=Depends(HTTPBearer()), db=Depends(get_db)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user