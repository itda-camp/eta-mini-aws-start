# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3", "joblib", "scikit-learn", "numpy"]
# ///
"""배치 예측: S3 의 주문 목록을 읽어 지금 승격된 판으로 한꺼번에 예측하고, 결과를 S3 에 쓴다.

서버를 띄워 두지 않는다. 일이 있을 때만 켜서 돌리고 끈다(`lab batch`).

    uv run training/batch_predict.py --bucket claude-eta-models --input batch/in/orders.csv --output batch/out/test/predictions.csv
    uv run training/batch_predict.py --make-input 100000 --bucket … --input batch/in/orders.csv     # 연습용 입력 만들기
"""

import argparse
import csv
import io
import json
import time

import boto3
import joblib
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--bucket", required=True)
parser.add_argument("--input", required=True, help="입력 CSV 의 키 (order_id,distance_km,pending_orders)")
parser.add_argument("--output", help="결과 CSV 의 키")
parser.add_argument("--impl", default="sklearn")
parser.add_argument("--make-input", type=int, metavar="N", help="예측하지 않고, N 건짜리 연습용 입력을 만들어 올린다")
args = parser.parse_args()

s3 = boto3.client("s3")

if args.make_input:
    rng = np.random.default_rng(0)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["order_id", "distance_km", "pending_orders"])
    for i, (d, p) in enumerate(zip(rng.uniform(0.5, 8.0, args.make_input), rng.integers(0, 11, args.make_input)), 1):
        w.writerow([i, f"{d:.2f}", int(p)])
    s3.put_object(Bucket=args.bucket, Key=args.input, Body=out.getvalue().encode(), ContentType="text/csv")
    print(json.dumps({"made": args.make_input, "key": args.input}))
    raise SystemExit

started = time.perf_counter()
prefix = f"models/{args.impl}"
version = json.loads(s3.get_object(Bucket=args.bucket, Key=f"{prefix}/current.json")["Body"].read())["version"]
s3.download_file(args.bucket, f"{prefix}/{version}/model.joblib", "/tmp/model.joblib")
model = joblib.load("/tmp/model.joblib")
label = f"{args.impl}@{version}"

rows = list(csv.DictReader(io.StringIO(s3.get_object(Bucket=args.bucket, Key=args.input)["Body"].read().decode())))
X = np.array([[float(r["distance_km"]), float(r["pending_orders"])] for r in rows], dtype=np.float32)
eta = model.predict(X)

out = io.StringIO()
w = csv.writer(out)
w.writerow(["order_id", "eta_minutes", "model"])  # 어느 판이 답했는지 줄마다 남긴다
for r, e in zip(rows, eta):
    w.writerow([r["order_id"], f"{e:.2f}", label])
s3.put_object(Bucket=args.bucket, Key=args.output, Body=out.getvalue().encode(), ContentType="text/csv")
print(json.dumps({"rows": len(rows), "model": label, "mean_eta": round(float(eta.mean()), 2), "seconds": round(time.perf_counter() - started, 2), "output": args.output}))
