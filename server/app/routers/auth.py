from __future__ import annotations

import re
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ADMIN_PASSWORD, COOKIE_SECURE, TOKEN_COOKIE, TOKEN_TTL_MINUTES
from ..db import get_db
from ..models import AdminUser
from ..schemas import LoginIn, MeOut, PasswordChangeIn
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录限流：内存记录，失败 5 次锁 15 分钟
_login_failures: dict[str, list[float]] = defaultdict(list)
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    failures = [t for t in _login_failures.get(ip, []) if now - t < LOCK_SECONDS]
    _login_failures[ip] = failures
    if len(failures) >= MAX_FAILURES:
        remaining = int(LOCK_SECONDS - (now - failures[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"失败次数太多，请 {remaining // 60 + 1} 分钟后再试",
        )


def _record_failure(ip: str) -> None:
    _login_failures[ip].append(time.time())


@router.post("/login", response_model=MeOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    user = db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        _record_failure(ip)
        # 不区分「没这个用户」和「口令错了」，别让人拿登录接口试账号
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或口令不对")

    # 登录成功，清空失败记录
    _login_failures.pop(ip, None)

    token = create_token(user.username)
    response.set_cookie(
        TOKEN_COOKIE,
        token,
        max_age=TOKEN_TTL_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )

    # 检测是否还是默认密码，返回标记
    needs_password_change = verify_password(ADMIN_PASSWORD, user.password_hash)
    return MeOut(username=user.username, needs_password_change=needs_password_change)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: AdminUser = Depends(current_user), db: Session = Depends(get_db)):
    needs_password_change = verify_password(ADMIN_PASSWORD, user.password_hash)
    return MeOut(username=user.username, needs_password_change=needs_password_change)


@router.post("/change-password")
def change_password(
    payload: PasswordChangeIn,
    user: AdminUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不对")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,118}$")


def check_slug(slug: str) -> str:
    """网址用的 slug：小写字母、数字、中划线。中文标题请在后台单独填英文 slug。"""
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(400, detail="slug 只能用 a-z、0-9 和中划线，且以字母或数字开头（它会长在网址里）")
    return slug
