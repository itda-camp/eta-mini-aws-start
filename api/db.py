"""DB 연결과 테이블 정의.

- 접속 문자열은 환경변수 DATABASE_URL 하나로 정한다. Compose 는 PostgreSQL,
  노트북에서 그냥 띄우거나 Mac Studio 에 올릴 때는 SQLite(기본값).
- 테이블은 셋 : users(비밀번호는 해시만), sessions(난수 ID), orders(예측 이력).
  01 「어디에 무엇을 저장하나」 표가 그대로 테이블이 된다.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eta.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# 커넥션 풀. SQLAlchemy 기본은 5 + 넘침 10 = 15. 스레드풀(40)보다 작아서 동시 요청이 많으면 여기서 먼저 줄을 선다
# DB_POOL_SIZE·DB_MAX_OVERFLOW 로 바꾼다.
_pool = {} if DATABASE_URL.startswith("sqlite") else {"pool_size": int(os.getenv("DB_POOL_SIZE", "5")), "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10"))}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True, **_pool)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # 비밀번호 원문은 어디에도 없다
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # admin | viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class UserSession(Base):
    """서버 세션. 쿠키에는 이 id(난수)만 담긴다. 이 행을 지우면 로그인은 즉시 무효가 된다."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class Order(Base):
    """예측 한 건 = 주문 한 건. 08 에서 입력 분포(distance_km)의 변화를 이 표로 본다."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    distance_km: Mapped[float] = mapped_column(Float)
    pending_orders: Mapped[int] = mapped_column(Integer)
    minutes: Mapped[float] = mapped_column(Float)
    model: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="orders")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    """요청마다 DB 세션 하나. FastAPI Depends 로 쓴다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
