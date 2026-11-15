"""세션 인증. 라이브러리 뒤에 숨기지 않고 직접 쓴다 — 흐름이 보여야 한다.

로그인  : 비밀번호 검증 → sessions 에 난수 행 추가 → Set-Cookie: sid=<난수>; HttpOnly; SameSite=Lax
요청    : 브라우저가 Cookie: sid=... 를 자동으로 붙인다 → sessions 에서 찾아 사용자를 안다
로그아웃: 브라우저 쿠키만 지운다. sessions 행은 남는다
"""

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from api.db import User, UserSession, get_db

COOKIE_NAME = "sid"
_hasher = PasswordHasher()


@dataclass(frozen=True)
class Principal:
    """「지금 요청한 사람」. 핸들러는 이 셋만 본다."""

    id: int
    username: str
    role: str


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def create_session(db: Session, user: User, response: Response) -> str:
    """세션 행을 만들고 쿠키를 내려준다. 쿠키 값은 추측할 수 없는 난수여야 한다."""
    sid = secrets.token_urlsafe(32)
    db.add(UserSession(id=sid, user_id=user.id))
    db.commit()
    response.set_cookie(
        key=COOKIE_NAME,
        value=sid,
        httponly=True,   # document.cookie 로 읽을 수 없다 (XSS 가 훔치지 못한다)
        samesite="lax",  # 다른 사이트에서 보낸 POST 에는 붙지 않는다 (CSRF 를 줄인다)
        secure=False,    # 실습은 http. 운영(https)에서는 True
        path="/",
    )
    return sid


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    """쿠키로 사용자를 찾는다. 없거나 모르는 값이면 401."""
    sid = request.cookies.get(COOKIE_NAME)
    if sid is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    session = db.get(UserSession, sid)
    if session is None:
        raise HTTPException(status_code=401, detail="세션이 없거나 만료되었습니다")
    return Principal(id=session.user.id, username=session.user.username, role=session.user.role)
