"""서비스할 모델을 정하고 불러온다.

- MODEL_S3_BUCKET 이 없으면(기본) : MODEL_IMPL 구현체를 바로 불러온다. 지금까지와 같다.
- MODEL_S3_BUCKET 이 있으면 : S3 의 `models/<구현체>/current.json` 이 가리키는 판을 받아 온 뒤 불러온다.
  받는 동안 /api/ready 는 503 이다. 이미지에 모델을 굽지 않으므로, 모델만 바꿔 배포할 수 있다.

    s3://<버킷>/models/sklearn/v1/model.joblib      판 하나 = 폴더 하나
    s3://<버킷>/models/sklearn/v1/metrics.json
    s3://<버킷>/models/sklearn/current.json         {"version": "v1"}  ← 지금 서비스할 판
"""

import importlib
import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("uvicorn.error")

MODEL_IMPL = os.getenv("MODEL_IMPL", "rule")
MODEL_S3_BUCKET = os.getenv("MODEL_S3_BUCKET", "")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "artifacts"))

_predict: Callable[[float, int], float] | None = None
_version: str | None = None
_error: str | None = None


def label() -> str:
    """어느 구현체의 어느 판이 답했는지. 예: `rule`, `sklearn@v2`."""
    return f"{MODEL_IMPL}@{_version}" if _version else MODEL_IMPL


def ready() -> bool:
    return _predict is not None


def error() -> str | None:
    return _error


def predict(distance_km: float, pending_orders: int) -> float:
    if _predict is None:
        raise RuntimeError("모델을 아직 불러오지 못했다")
    return _predict(distance_km, pending_orders)


def _download() -> str:
    """current.json 이 가리키는 판의 파일을 MODEL_DIR 로 받고, 판 이름을 돌려준다."""
    import boto3  # S3 를 쓸 때만 필요하다 (uv sync --group ml)

    s3 = boto3.client("s3")  # 키를 넣지 않는다 : 기본 자격 증명 체인(EC2 에서는 인스턴스 프로파일)
    prefix = f"models/{MODEL_IMPL}"
    pointer = json.loads(s3.get_object(Bucket=MODEL_S3_BUCKET, Key=f"{prefix}/current.json")["Body"].read())
    version = pointer["version"]
    listing = s3.list_objects_v2(Bucket=MODEL_S3_BUCKET, Prefix=f"{prefix}/{version}/")
    if not listing.get("Contents"):
        raise FileNotFoundError(f"s3://{MODEL_S3_BUCKET}/{prefix}/{version}/ 에 파일이 없다")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for old in MODEL_DIR.iterdir():  # 지난 판의 파일이 남아 있으면 새 판인 척 불려 온다
        if old.is_file():
            old.unlink()
    for obj in listing["Contents"]:
        name = obj["Key"].rsplit("/", 1)[-1]
        if name:
            s3.download_file(MODEL_S3_BUCKET, obj["Key"], str(MODEL_DIR / name))
    return version


def load() -> None:
    global _predict, _version, _error
    try:
        version = _download() if MODEL_S3_BUCKET else None
        module = importlib.import_module(f"api.predictors.{MODEL_IMPL}")
        _predict, _version, _error = module.estimate_delivery_minutes, version, None
        log.info("model loaded: %s", label())
    except Exception as exc:  # 받기에 실패해도 프로세스는 살아 있다. /api/ready 가 503 과 이유를 낸다
        _error = f"{type(exc).__name__}: {exc}"
        log.error("model load failed: %s", _error)


def load_in_background() -> None:
    threading.Thread(target=load, name="model-load", daemon=True).start()


if not MODEL_S3_BUCKET:
    load()  # 받을 것이 없으면 기다릴 것도 없다
