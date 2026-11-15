# eta-mini — 에이전트 작업 규칙

이 파일은 에이전트가 매 세션 읽는다. 팀의 기억이다. 규칙을 바꾸려면 이 파일을 고쳐라, 대화에서 부탁하지 말고.

## 이 저장소

배달 도착 예정시간(ETA) 미니 서비스. 브라우저 → nginx(8080) → `/` 는 React 정적 파일, `/api/*` 는 FastAPI(8000) → PostgreSQL(5432).

| 폴더 | 내용 | 명령 |
| --- | --- | --- |
| `api/` | FastAPI. `app.py`(경로), `auth.py`(세션 인증), `db.py`(테이블), `predictors/`(예측 구현체) | `uv run uvicorn api.app:app --reload --port 8000` |
| `api/tests/` | pytest. 계약(상태 코드·응답 형식·규칙 값)을 테스트한다 | `uv run pytest -q` |
| `web/` | Vite React. `src/api.js` 가 서버와 말하는 유일한 곳 | `cd web && npm run dev` (5173, `/api` 는 8000 으로 프록시) |
| `training/` | 학습(`train_sklearn`)·검증 게이트(`validate_model`)·배치 예측·GPU 벤치마크 | `uv run --group ml python -m training.train_sklearn` |
| `infra/aws/` | AWS 실습 도우미 `lab` 과 수강생 정책 틀(`student/`) | `uv run --group ml lab --help` |
| `.github/workflows/aws.yml` | 테스트 → 학습·검증·모델 승격 → 이미지 push·EC2 갱신 | |

전체 띄우기 : `cp .env.example .env` → `docker compose up -d --build` → http://localhost:8080 (API 문서 `/api/docs`).

## 하지 않는 것

- `pip`, `python -m venv`, `requirements.txt` 를 쓰지 않는다. 파이썬은 **`uv` 만** : 의존성은 `uv add`, 실행은 `uv run`.
- `.env` 를 읽지도, 출력하지도, 커밋하지도 않는다. 값이 필요하면 사용자에게 **이름만** 묻는다.
- `docker compose down -v`(데이터 삭제), `rm -rf`, `git push --force` 는 하지 않는다. 필요하면 사용자가 직접 한다.
- 테스트를 통과시키려고 테스트를 고치거나 지우지 않는다. 실패하면 원인을 보고하고 멈춘다.
- 포트는 8080(web)·8000(api)·5432(db) 고정. 바꾸지 않는다.
- 인증·세션 코드(`api/auth.py`)는 설명 없이 바꾸지 않는다. 바꾸면 **무엇이 더 안전해지는지/덜 안전해지는지** 한 줄을 PR 에 쓴다.

## 작업을 마치기 전에

1. `uv run pytest -q` 결과를 보여 준다. 화면을 고쳤으면 `cd web && npm run build` 도.
2. 바꾼 동작은 **명령어로 증거**를 남긴다 : `curl -i ...` 응답, 또는 `docker compose logs api` 의 해당 줄.
3. 모르는 코드가 있었으면 「이 줄은 왜 있는가」를 설명할 수 있어야 한다. 설명 못 하는 코드는 넣지 않는다.
4. 무엇을 했고 무엇을 하지 않았는지 세 줄로 정리한다.

## 커밋과 PR

- 커밋은 한 가지 변경에 하나. 메시지는 한국어 한 줄 : `로그아웃 시 세션 행 삭제`.
- 커밋 전에 `uv run pytest -q` 가 자동으로 돈다(`.claude/settings.json` 의 훅). 실패하면 커밋되지 않는다.
- PR 본문 : **왜**(무엇이 문제였나) · **무엇을**(바꾼 파일) · **증거**(테스트·curl) · **안 한 것**.

## 모르면 묻는다

요구가 둘로 읽히면 짐작하지 말고 묻는다. 「로그인 기능 고쳐 줘」는 작업이 아니다. 목표·대상·금지·끝 조건(명령어로 확인되는 것)을 다시 받아라.
