"""테스트는 임시 SQLite 파일 하나로 돈다. PostgreSQL 도, 실제 서버도 띄우지 않는다."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("MODEL_IMPL", "rule")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "admin-test")
    monkeypatch.setenv("SEED_VIEWER_PASSWORD", "viewer-test")
    import api.db
    import api.auth
    import api.seed
    import api.model
    import api.app

    importlib.reload(api.db)
    importlib.reload(api.auth)
    importlib.reload(api.seed)
    importlib.reload(api.model)
    app_module = importlib.reload(api.app)
    with TestClient(app_module.app) as c:  # with 블록이 lifespan(테이블 생성·시드)을 돌린다
        yield c


def login(client, username="viewer", password="viewer-test"):
    res = client.post("/api/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res
