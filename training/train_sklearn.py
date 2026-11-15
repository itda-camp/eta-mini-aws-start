"""scikit-learn 학습: 배달 기록 수집 → 분할 → 정규화+학습 → 평가 → 저장.

같은 seed 로 다시 돌리면 같은 모델이 나온다(재현성). 02 의 학습 코드와 같다.

    uv run --group ml python -m training.train_sklearn            # artifacts/model.joblib, metrics.json
    uv run --group ml python -m training.train_sklearn --n 5000   # 데이터를 늘려 다른 판을 만든다
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from api.predictors import rule
from training.data import collect_data

parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=500, help="배달 기록 건수")
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--out", default="artifacts")
args = parser.parse_args()

X, y = collect_data(n=args.n, seed=args.seed)
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=0)
model = make_pipeline(StandardScaler(), LinearRegression())  # 정규화를 모델 안에
model.fit(X_tr, y_tr)

mae = float(np.abs(model.predict(X_te) - y_te).mean())
baseline = float(np.abs(np.array([rule.estimate_delivery_minutes(a, b) for a, b in X_te]) - y_te).mean())

out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
joblib.dump(model, out / "model.joblib")
(out / "metrics.json").write_text(
    json.dumps({"model": "sklearn", "n": args.n, "seed": args.seed, "mae": mae, "baseline_mae": baseline}, indent=2) + "\n"
)
print(f"sklearn 평균 오차 {mae:.2f}분  (기준선 rule {baseline:.2f}분)")
