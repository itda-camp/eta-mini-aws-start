import os

import joblib

_model = joblib.load(os.path.join(os.getenv("MODEL_DIR", "artifacts"), "model.joblib"))


def estimate_delivery_minutes(distance_km: float, pending_orders: int) -> float:
    """학습된 scikit-learn 파이프라인으로 배달 예상 시간(분)을 계산한다.

    파이프라인 안에 StandardScaler 가 들어 있으므로 원래 단위의 값을 그대로 넣는다.
    모델 파일은 training.train_sklearn 이 만들고, 운영에서는 api.model 이 S3 에서 받아 둔다.
    """
    return float(_model.predict([[distance_km, pending_orders]])[0])
