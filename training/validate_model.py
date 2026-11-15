"""모델 검증 게이트. 실패(exit 1)하면 이후 단계(S3 업로드·승격)가 진행되지 않는다.

    uv run python -m training.validate_model

통과 조건
  1) 기준선(사장님 규칙)보다 평균 오차가 작을 것
  2) 절대 기준: 평균 오차(MAE) < MAX_MAE 분
"""

import json
import sys
from pathlib import Path

MAX_MAE = 2.0  # 분. 평균 2분 넘게 틀리면 배포하지 않는다

m = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/metrics.json").read_text())
checks = {
    f"기준선보다 나은가 ({m['mae']:.2f}분 < {m['baseline_mae']:.2f}분)": m["mae"] < m["baseline_mae"],
    f"절대 기준 통과 ({m['mae']:.2f}분 < {MAX_MAE}분)": m["mae"] < MAX_MAE,
}
for desc, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + desc)
sys.exit(0 if all(checks.values()) else 1)
