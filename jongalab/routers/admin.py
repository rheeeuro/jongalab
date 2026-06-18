"""관리자 라우트"""
import hashlib
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# 세션 토큰 = sha256(ADMIN_PASSWORD). 비번을 모르면 계산 불가 → 위조 불가.
# 로그인 성공 시 프론트가 httpOnly 쿠키로 보관하고 admin 엔드포인트에 Bearer 로 전달한다.
SESSION_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest() if ADMIN_PASSWORD else ""


def require_admin(request: Request):
    """admin 엔드포인트 보호 의존성 — 유효한 Bearer 토큰을 요구한다."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth[:7].lower() == "bearer " else ""
    if not SESSION_TOKEN or token != SESSION_TOKEN:
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def admin_login(req: LoginRequest):
    """관리자 비밀번호 검증. 성공 시 세션 토큰 발급(프론트가 httpOnly 쿠키로 보관)."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="Admin password not configured")
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"ok": True, "token": SESSION_TOKEN}


@router.get("/verify", dependencies=[Depends(require_admin)])
def admin_verify():
    """현재 세션 토큰 유효성 확인 — AdminLayout 이 마운트 시 호출."""
    return {"ok": True}
