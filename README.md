# eta-mini — 배달 도착 예정시간 미니 서비스

> **AI Campus MLOps 03 「AWS 기반 ML 인프라 구축」 실습의 시작점입니다.** 각자 clone 해서 교안 순서대로 따라갑니다. ⑤ 단계(GitHub Actions)부터는 이 저장소를 템플릿으로 내 비공개 저장소를 만들어 씁니다.

02 에서 만든 `eta-api`(규칙 : 기본 10분 + 1km 당 3분 + 대기 주문 1건당 2분, 그리고 scikit-learn 모델)에 **화면·사용자·DB** 를 붙이고, AWS 실습 도구(`infra/aws/`)와 배포 워크플로(`.github/workflows/aws.yml`)를 더한 것.

```text
브라우저 ──> nginx:8080 ──┬── /            React 빌드 결과(정적)
                          └── /api/*       FastAPI:8000 ──> PostgreSQL:5432
```

## 띄우기

```sh
git clone https://github.com/itda-camp/eta-mini-aws-start.git && cd eta-mini-aws-start
cp .env.example .env            # 비밀번호 바꾸기
docker compose up -d --build
docker compose ps
open http://localhost:8080      # 로그인 viewer / viewer1234 (admin / admin1234)
```

- API 문서 : http://localhost:8080/api/docs
- 로그 : `docker compose logs -f api`

## 읽는 순서 (30분)

1. `web/nginx.conf` — 요청이 어디로 갈라지나
2. `api/app.py` — 경로와 스키마(= 계약). `/api/docs` 와 나란히
3. `api/auth.py` — 로그인에서 쿠키가 나와서, 다음 요청에서 사용자가 되기까지 60줄
4. `api/db.py` — 표 세 개 : users(해시만), sessions(난수), orders(이력)
5. `web/src/api.js` → `web/src/App.jsx` — 화면이 서버와 말하는 유일한 통로, 그리고 라우팅

브라우저 개발자 도구 Network 탭에서 `/api/login` 의 응답 헤더 `Set-Cookie` 와 다음 요청의 `Cookie` 를 보라. 콘솔에서 `document.cookie` 는 비어 있다(HttpOnly).

## 로컬에서 도커 없이

```sh
uv sync && uv run uvicorn api.app:app --reload --port 8000   # SQLite(eta.db) 로 뜬다
cd web && npm ci && npm run dev                               # 5173, /api 는 8000 으로 프록시
```

## 에이전트와 일하기

- `CLAUDE.md` — 이 저장소의 규칙. 에이전트가 매번 읽는다.
- `.claude/settings.json` — 허용·거부 명령과 커밋 전 테스트 훅.
- `.claude/skills/eta-aws-lab/` — 수업 계정에서 자원을 만들고·배포하고·지울 때의 약속.

## 학습과 AWS 실습 도구

```sh
uv run --group ml python -m training.train_sklearn   # artifacts/model.joblib, metrics.json
uv run python -m training.validate_model             # 검증 게이트. 실패하면 종료 코드 1
uv run --group ml lab --help                         # AWS 실습 도우미(infra/aws/lab.py)
```

## 테스트

```sh
uv run pytest -q       # 임시 SQLite 로 돈다. PostgreSQL 불필요
```

실행 확인 : 2026-11-16, macOS + Colima, Docker 29.8, Node 26, uv 0.12, Python 3.14.
