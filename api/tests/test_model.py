"""api.model : S3 의 current.json 이 가리키는 판을 받아 오는 부분. S3 는 가짜로 바꿔 끼운다."""

import importlib
import io
import json

import pytest


class FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, Bucket, Prefix):
        keys = [k for k in self.objects if k.startswith(Prefix)]
        return {"Contents": [{"Key": k} for k in keys]} if keys else {}

    def download_file(self, Bucket, Key, Filename):
        with open(Filename, "wb") as f:
            f.write(self.objects[Key])


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_IMPL", "rule")
    monkeypatch.setenv("MODEL_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    import api.model

    return importlib.reload(api.model)


def use(monkeypatch, objects):
    import boto3

    monkeypatch.setattr(boto3, "client", lambda name: FakeS3(objects))


def test_downloads_the_version_current_json_points_to(model, monkeypatch):
    use(monkeypatch, {
        "models/rule/current.json": json.dumps({"version": "v2"}).encode(),
        "models/rule/v1/model.joblib": b"one",
        "models/rule/v2/model.joblib": b"two",
    })
    model.load()
    assert model.ready() and model.label() == "rule@v2"
    assert (model.MODEL_DIR / "model.joblib").read_bytes() == b"two"


def test_missing_version_is_not_ready_and_does_not_reuse_old_files(model, monkeypatch):
    """current.json 이 없는 판을 가리키면, 지난 판의 파일이 남아 있어도 준비 안 됨이어야 한다."""
    use(monkeypatch, {"models/rule/current.json": json.dumps({"version": "v1"}).encode(), "models/rule/v1/model.joblib": b"one"})
    model.load()
    assert model.label() == "rule@v1"

    broken = importlib.reload(model)
    use(monkeypatch, {"models/rule/current.json": json.dumps({"version": "broken"}).encode()})
    broken.load()
    assert not broken.ready()
    assert "broken" in broken.error()
