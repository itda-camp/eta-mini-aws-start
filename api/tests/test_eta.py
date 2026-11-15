"""/api/eta 와 /api/orders 의 계약. 기대값은 규칙(10 + 3×거리 + 2×주문)을 손으로 계산한 것."""

import pytest

from api.tests.conftest import login


def test_eta_requires_login(client):
    """로그인 없이 /api/eta 는 401."""
    assert client.post("/api/eta", json={"distance_km": 3, "pending_orders": 2}).status_code == 401


@pytest.mark.parametrize(
    ("distance_km", "pending_orders", "expected"),
    [(0, 0, 10.0), (3, 2, 23.0), (2.5, 4, 25.5), (20, 100, 270.0)],
)
def test_eta_rule_values(client, distance_km, pending_orders, expected):
    """알려진 입력에 대해 규칙 값과 model=rule 을 돌려준다(201)."""
    login(client)
    res = client.post("/api/eta", json={"distance_km": distance_km, "pending_orders": pending_orders})
    assert res.status_code == 201
    body = res.json()
    assert body["minutes"] == pytest.approx(expected)
    assert body["model"] == "rule"
    assert isinstance(body["order_id"], int)


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": -1, "pending_orders": 0},
        {"distance_km": 21, "pending_orders": 0},
        {"distance_km": 1, "pending_orders": -1},
        {"distance_km": "far", "pending_orders": 0},
        {"pending_orders": 0},
    ],
)
def test_eta_invalid_input_is_422(client, payload):
    """음수·범위 초과·타입 오류·빠진 필드는 422."""
    login(client)
    assert client.post("/api/eta", json=payload).status_code == 422


def test_eta_appends_to_my_orders_only(client):
    """예측 한 번은 내 이력에 한 건 추가되고, 다른 사용자의 이력에는 보이지 않는다."""
    login(client, "viewer", "viewer-test")
    before = len(client.get("/api/orders").json())
    client.post("/api/eta", json={"distance_km": 1, "pending_orders": 1})
    mine = client.get("/api/orders").json()
    assert len(mine) == before + 1
    assert mine[0]["minutes"] == pytest.approx(15.0)  # 최신순

    client.cookies.clear()
    login(client, "admin", "admin-test")
    theirs = client.get("/api/orders").json()
    assert all(o["id"] != mine[0]["id"] for o in theirs)


def test_seed_orders_exist(client):
    """첫 실행 시드로 두 계정 합쳐 주문 20건이 들어 있다."""
    login(client, "viewer", "viewer-test")
    n_viewer = len(client.get("/api/orders").json())
    client.cookies.clear()
    login(client, "admin", "admin-test")
    n_admin = len(client.get("/api/orders").json())
    assert n_viewer + n_admin == 20

