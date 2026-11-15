"""eta-mini API.

경로는 모두 /api 아래 : nginx 가 /api/* 만 이쪽으로 넘긴다(web/nginx.conf).
"""

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import auth, model
from api.db import Order, SessionLocal, User, get_db, init_db
from api.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed(db)
    if not model.ready():
        model.load_in_background()  # S3 에서 받는 동안에도 서버는 뜬다. 그동안 /api/ready 는 503
    yield


app = FastAPI(
    title="eta-mini",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ 스키마 (= 계약)


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=4, max_length=128)


class Me(BaseModel):
    id: int
    username: str
    role: str


class EtaRequest(BaseModel):
    """02 의 EtaRequest 와 같다. 모델이 더 많은 정보를 원하면 여기에 필드를 추가."""

    distance_km: float = Field(ge=0, le=20, allow_inf_nan=False, description="가게에서 배달지까지 거리(km)")
    pending_orders: int = Field(ge=0, le=100, description="지금 밀려 있는 주문 수")


class EtaResponse(BaseModel):
    order_id: int
    minutes: float
    model: str


class OrderOut(BaseModel):
    id: int
    distance_km: float
    pending_orders: int
    minutes: float
    model: str
    created_at: str


# ------------------------------------------------------------------ 상태


@router.get("/health")
def health() -> dict[str, str]:
    """살아 있는가(liveness). 프로세스가 답하면 200. 모델 판을 함께 낸다."""
    return {"status": "ok", "model": model.label()}


@router.get("/ready")
def ready(response: Response) -> dict[str, str]:
    """요청을 받을 준비가 됐는가(readiness). 모델을 받는 중이거나 받기에 실패했으면 503."""
    if model.ready():
        return {"status": "ready", "model": model.label()}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "loading" if model.error() is None else "failed", "detail": model.error() or ""}


# ------------------------------------------------------------------ 계정과 세션


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=Me)
def register(body: Credentials, db: Session = Depends(get_db)) -> Me:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=409, detail="이미 있는 아이디입니다")
    user = User(username=body.username, password_hash=auth.hash_password(body.password), role="viewer")
    db.add(user)
    db.commit()
    return Me(id=user.id, username=user.username, role=user.role)


@router.post("/login", response_model=Me)
def login(body: Credentials, response: Response, db: Session = Depends(get_db)) -> Me:
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not auth.verify_password(body.password, user.password_hash):
        # 아이디가 없는지 비밀번호가 틀렸는지 알려주지 않는다
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 맞지 않습니다")
    auth.create_session(db, user, response)
    return Me(id=user.id, username=user.username, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """브라우저의 쿠키를 지운다. sessions 행은 남는다."""
    auth.clear_session_cookie(response)


@router.get("/me", response_model=Me)
def me(user: auth.Principal = Depends(auth.current_user)) -> Me:
    return Me(id=user.id, username=user.username, role=user.role)


# ------------------------------------------------------------------ 예측과 이력


@router.post("/eta", response_model=EtaResponse, status_code=status.HTTP_201_CREATED)
def eta(req: EtaRequest, user: auth.Principal = Depends(auth.current_user), db: Session = Depends(get_db)) -> EtaResponse:
    """예측하고, 그 결과를 주문 이력으로 남긴다."""
    if not model.ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "모델을 불러오는 중입니다")
    minutes = model.predict(req.distance_km, req.pending_orders)
    order = Order(
        user_id=user.id,
        distance_km=req.distance_km,
        pending_orders=req.pending_orders,
        minutes=minutes,
        model=model.label(),
    )
    db.add(order)
    db.commit()
    return EtaResponse(order_id=order.id, minutes=minutes, model=model.label())


@router.get("/orders", response_model=list[OrderOut])
def orders(user: auth.Principal = Depends(auth.current_user), db: Session = Depends(get_db)) -> list[OrderOut]:
    """내 주문만, 최신순."""
    rows = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())).all()
    return [
        OrderOut(
            id=o.id,
            distance_km=o.distance_km,
            pending_orders=o.pending_orders,
            minutes=o.minutes,
            model=o.model,
            created_at=o.created_at.isoformat(),
        )
        for o in rows
    ]


app.include_router(router)
