"""
app/api/routes/auth.py
POST /auth/login → JWT token
"""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from app.db.database import get_db
from app.models.schemas import LoginRequest, TokenResponse
from app.core.security import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, conn: asyncpg.Connection = Depends(get_db)):
    row = await conn.fetchrow(
        "SELECT id, hashed_pw FROM users WHERE username=$1", payload.username
    )

    if not row or not verify_password(payload.password, row["hashed_pw"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": payload.username, "uid": row["id"]})
    return TokenResponse(access_token=token)
