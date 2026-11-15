"""세션 인증의 HTTP 계약. 구현(argon2, 테이블 이름)이 아니라 상태 코드와 쿠키 동작을 본다."""

from api.tests.conftest import login


def test_me_without_cookie_is_401(client):
    """로그인 전 /api/me 는 401."""
    assert client.get("/api/me").status_code == 401


def test_login_sets_httponly_cookie_and_me_works(client):
    """로그인하면 HttpOnly 세션 쿠키가 내려오고, 그 뒤 /api/me 가 200."""
    res = login(client)
    set_cookie = res.headers["set-cookie"].lower()
    assert "sid=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    me = client.get("/api/me").json()
    assert (me["username"], me["role"]) == ("viewer", "viewer") and isinstance(me["id"], int)


def test_login_wrong_password_is_401(client):
    """비밀번호가 틀리면 401. 아이디가 없는 경우와 같은 메시지."""
    bad = client.post("/api/login", json={"username": "viewer", "password": "nope-nope"})
    none = client.post("/api/login", json={"username": "ghost", "password": "nope-nope"})
    assert bad.status_code == none.status_code == 401
    assert bad.json() == none.json()


def test_unknown_sid_is_401(client):
    """아무 값이나 넣은 sid 쿠키는 통하지 않는다."""
    client.cookies.set("sid", "not-a-real-session")
    assert client.get("/api/me").status_code == 401


def test_register_then_login(client):
    """가입(201) → 로그인(200) → me 의 role 은 viewer."""
    res = client.post("/api/register", json={"username": "newbie", "password": "pass1234"})
    assert res.status_code == 201
    login(client, "newbie", "pass1234")
    assert client.get("/api/me").json()["role"] == "viewer"


def test_register_duplicate_is_409(client):
    """같은 아이디로 두 번 가입하면 409."""
    assert client.post("/api/register", json={"username": "viewer", "password": "pass1234"}).status_code == 409


def test_register_validation_422(client):
    """아이디 규칙(소문자·숫자·_)과 비밀번호 길이를 어기면 422."""
    assert client.post("/api/register", json={"username": "Bad Name", "password": "pass1234"}).status_code == 422
    assert client.post("/api/register", json={"username": "ok_name", "password": "abc"}).status_code == 422


def test_logout_clears_browser_cookie(client):
    """로그아웃(204) 뒤 브라우저(쿠키 저장소)는 sid 를 잃고, 다음 /api/me 는 401.

    주의 : 이 테스트는 '브라우저가 쿠키를 지웠다' 만 본다. 로그아웃 전의 sid 값을 따로 들고 있다가
    다시 보내면 여전히 통한다(서버의 sessions 행을 지우지 않는다).
    """
    login(client)
    assert client.post("/api/logout").status_code == 204
    assert client.get("/api/me").status_code == 401
