from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    user_to_response,
)
from backend.database import get_db
from backend.models import User, PasswordResetToken
from backend.schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from backend.config import TRIAL_DAYS, BASE_URL
from backend.services.charlotte import welcome_email, password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid4())
    trial_ends = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    user = User(
        id=user_id,
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        first_name=req.first_name,
        last_name=req.last_name,
        company=req.company,
        industry=req.industry,
        province=req.province,
        plan="trial",
        trial_ends_at=trial_ends,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    welcome_email(user.email, user.first_name)
    token = create_access_token(data={"sub": user.id})
    return TokenResponse(access_token=token, user=UserResponse(**user_to_response(user)))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(data={"sub": user.id})
    return TokenResponse(access_token=token, user=UserResponse(**user_to_response(user)))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(**user_to_response(user))


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if user:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.query(PasswordResetToken).filter(PasswordResetToken.email == user.email).delete()
        db.add(PasswordResetToken(token=token, email=user.email, expires_at=expires))
        db.commit()
        reset_url = f"{BASE_URL.rstrip('/')}/reset-password?token={token}"
        password_reset_email(user.email, reset_url, user.first_name)
    return {"message": "If an account exists, you will receive reset instructions."}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == req.token,
        PasswordResetToken.expires_at > datetime.now(timezone.utc),
    ).first()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user = db.query(User).filter(User.email == row.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    user.password_hash = hash_password(req.new_password)
    db.query(PasswordResetToken).filter(PasswordResetToken.token == req.token).delete()
    db.commit()
    return {"message": "Password updated. You can log in now."}
