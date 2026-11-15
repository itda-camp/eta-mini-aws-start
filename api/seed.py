"""첫 실행 시 기본 계정과 주문 20건을 넣는다. 비밀번호는 환경변수에서 읽는다(.env.example 참고)."""

import os
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import hash_password
from api.db import Order, User
from api.predictors.rule import estimate_delivery_minutes


def seed(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    admin = User(username="admin", password_hash=hash_password(os.getenv("SEED_ADMIN_PASSWORD", "admin1234")), role="admin")
    viewer = User(username="viewer", password_hash=hash_password(os.getenv("SEED_VIEWER_PASSWORD", "viewer1234")), role="viewer")
    db.add_all([admin, viewer])
    db.flush()

    rng = random.Random(42)  # 같은 시드 → 같은 20건. 수업에서 화면이 서로 같아야 한다
    for _ in range(20):
        distance = round(rng.uniform(1.0, 3.0), 1)
        pending = rng.randint(0, 5)
        db.add(Order(
            user_id=rng.choice([admin.id, viewer.id]),
            distance_km=distance,
            pending_orders=pending,
            minutes=estimate_delivery_minutes(distance, pending),
            model="rule",
        ))
    db.commit()
