# 빌드 컨텍스트는 저장소 루트(docker-compose.yml 의 context: .)
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# 의존성만 먼저 설치해 코드가 바뀌어도 이 층은 캐시된다
# --group ml : scikit-learn·boto3. MODEL_IMPL=sklearn 과 S3 모델 저장소에 쓴다
RUN uv sync --locked --no-dev --group ml --no-cache --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
COPY api/ api/
# 모델 파일은 이미지에 굽지 않는다. 시작할 때 S3 에서 받는다(api/model.py)
ENV MODEL_DIR=/tmp/models
ARG MODEL_IMPL=rule
ENV MODEL_IMPL=${MODEL_IMPL}
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
