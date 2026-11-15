# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "numpy"]
# ///
"""같은 학습을 크기만 키워 가며 재서, 어느 크기부터 GPU 가 이득인지 본다.

프로젝트 설치 없이 이 파일 하나로 돈다(위 주석이 의존성 — uv 가 알아서 받는다).

    uv run training/bench_torch.py                         # 쓸 수 있는 장치(cuda → mps → cpu)
    uv run training/bench_torch.py --device cpu            # CPU 로 고정
    uv run training/bench_torch.py --sizes 200000x256 2000000x1024

모델은 02 의 딥러닝 구현체와 같은 꼴(입력 2 → 은닉층 둘 → 출력 1)이고, 데이터는 같은 식으로 만든다.
"""

import argparse
import json
import platform
import time

import numpy as np
import torch


def make_data(n: int, seed: int = 0) -> tuple[torch.Tensor, torch.Tensor]:
    rng = np.random.default_rng(seed)
    distance_km = rng.uniform(0.5, 8.0, n)
    pending_orders = rng.integers(0, 11, n).astype(float)
    minutes = 12 + 3 * distance_km + 4 * pending_orders + rng.normal(0, 1.5, n)
    x = np.column_stack([distance_km, pending_orders]).astype(np.float32)
    return torch.from_numpy(x), torch.from_numpy(minutes.astype(np.float32)).unsqueeze(1)


def train(n: int, hidden: int, epochs: int, batch: int, device: torch.device) -> dict:
    torch.manual_seed(0)
    x, y = make_data(n)
    started = time.perf_counter()
    x, y = x.to(device), y.to(device)
    mean, std = x.mean(0), x.std(0)
    model = torch.nn.Sequential(
        torch.nn.Linear(2, hidden), torch.nn.ReLU(), torch.nn.Linear(hidden, hidden), torch.nn.ReLU(), torch.nn.Linear(hidden, 1)
    ).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    for _ in range(epochs):
        order = torch.randperm(n, device=device)
        for i in range(0, n, batch):
            idx = order[i : i + batch]
            opt.zero_grad()
            loss = torch.nn.functional.mse_loss(model((x[idx] - mean) / std), y[idx])
            loss.backward()
            opt.step()
    with torch.no_grad():  # 평가도 나눠서 : 200만 건 × 은닉 1024 를 한 번에 넣으면 T4(16GB)의 메모리가 넘친다
        errors = [(model((x[i : i + 65536] - mean) / std) - y[i : i + 65536]).abs().sum() for i in range(0, n, 65536)]
        mae = (torch.stack(errors).sum() / n).item()  # .item() 이 GPU 작업이 끝나기를 기다린다
    return {"n": n, "hidden": hidden, "epochs": epochs, "seconds": round(time.perf_counter() - started, 2), "mae": round(mae, 2)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", default=["20000x64", "200000x256", "2000000x256", "2000000x1024"], help="건수x은닉층 크기")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch", type=int, default=4096)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    args = parser.parse_args()

    name = args.device
    if name == "auto":
        name = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    device = torch.device(name)
    label = torch.cuda.get_device_name(0) if name == "cuda" else f"{platform.machine()} {name}"
    print(json.dumps({"device": name, "label": label, "torch": torch.__version__, "threads": torch.get_num_threads()}), flush=True)
    for size in args.sizes:
        n, hidden = (int(v) for v in size.split("x"))
        print(json.dumps(train(n, hidden, args.epochs, args.batch, device)), flush=True)


if __name__ == "__main__":
    main()
