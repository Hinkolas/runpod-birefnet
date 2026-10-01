# /// script
# requires-python = ">=3.12"
# dependencies = ["requests>=2.34"]
# ///
"""End-to-end latency benchmark for a deployed runpod-birefnet endpoint.

Every request records the client-side wall time and splits it into RunPod's own
`delayTime` (queueing + cold start), `executionTime` (the handler), and the rest
(network + RunPod API overhead), next to the worker's per-stage `timings`.

Scenarios:
    warm   N sequential requests against an endpoint that already has a worker up.
    cold   Wait until the endpoint has scaled to zero workers, then send one request.
           Repeat K times. Shows what a request pays after the endpoint went idle.
    burst  C requests at once, to see queueing and scale-up.

Usage:
    export RUNPOD_API_KEY=... RUNPOD_ENDPOINT_ID=...
    uv run bench/latency.py warm --n 20
    uv run bench/latency.py cold --k 3
    uv run bench/latency.py burst --c 8
    uv run bench/latency.py warm --n 20 --transport http --model lite
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.runpod.ai/v2"
IMAGE_BASE = "https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main"
IMAGES = [
    "tiger.jpg",
    "corgi.jpg",
    "cats.jpg",
    "football-match.jpg",
    "portrait-of-woman_small.jpg",
    "bread_small.png",
    "butterfly.jpg",
]
HERE = Path(__file__).parent
CACHE = HERE / ".cache"
RESULTS = HERE / "results"


class Endpoint:
    def __init__(self, base: str, api_key: str) -> None:
        self.base = base
        self.api_key = api_key
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        # One keep-alive session per thread, like a real client would reuse connections.
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
            self._local.session.headers["Authorization"] = f"Bearer {self.api_key}"
        return self._local.session

    def health(self) -> dict:
        response = self.session.get(f"{self.base}/health", timeout=30)
        response.raise_for_status()
        return response.json()

    def run(self, job_input: dict, poll_interval: float = 0.25) -> tuple[dict, float]:
        """Submit via /runsync (falling back to /status polling). Returns (final status, e2e ms)."""
        started = time.perf_counter()
        response = self.session.post(f"{self.base}/runsync", json={"input": job_input}, timeout=600)
        response.raise_for_status()
        result = response.json()
        # /runsync gives up waiting after a while and returns the job still queued/running.
        while result.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
            time.sleep(poll_interval)
            response = self.session.get(f"{self.base}/status/{result['id']}", timeout=60)
            response.raise_for_status()
            result = response.json()
        return result, (time.perf_counter() - started) * 1000


def image_bytes(name: str) -> bytes:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / name
    if not path.exists():
        response = requests.get(f"{IMAGE_BASE}/{name}", timeout=60)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path.read_bytes()


def job_input(args, index: int) -> dict:
    name = IMAGES[index % len(IMAGES)]
    if args.transport == "base64":
        source = {"type": "base64", "data": base64.b64encode(image_bytes(name)).decode("ascii")}
    else:
        source = {"type": "http", "url": f"{IMAGE_BASE}/{name}"}
    outputs = [{"kind": kind, "format": "png"} for kind in args.outputs.split(",")]
    return {
        "source": source,
        "model": args.model,
        "outputs": outputs,
        "metadata": {"bench": args.scenario, "image": name},
    }


def record(args, index: int, result: dict, e2e_ms: float) -> dict:
    output = result.get("output") or {}
    delay = result.get("delayTime")
    execution = result.get("executionTime")
    row = {
        "scenario": args.scenario,
        "index": index,
        "status": result.get("status"),
        "error": result.get("error"),
        "image": IMAGES[index % len(IMAGES)],
        "model": args.model,
        "transport": args.transport,
        "e2eMs": round(e2e_ms, 1),
        "delayMs": delay,
        "executionMs": execution,
        "overheadMs": round(e2e_ms - delay - execution, 1) if delay is not None and execution is not None else None,
        "timings": output.get("timings"),
        "worker": output.get("worker"),
        "outputBytes": [o.get("bytes") for o in output.get("outputs", [])],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    worker = row["worker"] or {}
    cold = "COLD" if worker.get("coldStart") else "warm"
    print(
        f"#{index:<3} {row['status']:<9} e2e {row['e2eMs']:>8.0f} ms  delay {delay or 0:>7} ms  "
        f"exec {execution or 0:>6} ms  overhead {row['overheadMs'] or 0:>6.0f} ms  "
        f"infer {((row['timings'] or {}).get('inferenceMs') or 0):>6.0f} ms  "
        f"{cold} job {worker.get('jobIndex')} on {worker.get('device')}",
        flush=True,
    )
    return row


def wait_for_zero_workers(endpoint: Endpoint, max_wait: float) -> float:
    """Block until the endpoint reports no idle/running workers. Returns seconds waited."""
    started = time.time()
    while True:
        workers = endpoint.health().get("workers", {})
        busy = sum(v for k, v in workers.items() if k in ("idle", "running", "initializing", "ready") and isinstance(v, int))
        if busy == 0:
            return time.time() - started
        if time.time() - started > max_wait:
            raise TimeoutError(f"endpoint still has workers after {max_wait:.0f}s: {workers}")
        time.sleep(5)


def summarize(rows: list[dict]) -> None:
    ok = [r for r in rows if r["status"] == "COMPLETED"]
    if len(ok) != len(rows):
        print(f"\n{len(rows) - len(ok)} of {len(rows)} requests did not complete")
    if not ok:
        return

    def column(getter):
        values = [v for v in (getter(r) for r in ok) if v is not None]
        if not values:
            return None
        values.sort()
        p90 = values[min(len(values) - 1, round(0.9 * (len(values) - 1)))]
        return statistics.median(values), p90, values[-1]

    print(f"\n{'component (ms)':24s} {'p50':>8s} {'p90':>8s} {'max':>8s}")
    for label, getter in [
        ("client end-to-end", lambda r: r["e2eMs"]),
        ("runpod delay (queue+cold)", lambda r: r["delayMs"]),
        ("runpod execution", lambda r: r["executionMs"]),
        ("network + API overhead", lambda r: r["overheadMs"]),
        ("handler total", lambda r: (r["timings"] or {}).get("totalMs")),
        ("  download", lambda r: (r["timings"] or {}).get("downloadMs")),
        ("  inference", lambda r: (r["timings"] or {}).get("inferenceMs")),
        ("  encode", lambda r: (r["timings"] or {}).get("encodeMs")),
        ("worker startup", lambda r: (r["worker"] or {}).get("startupMs") if (r["worker"] or {}).get("coldStart") else None),
    ]:
        stats = column(getter)
        if stats:
            print(f"{label:24s} {stats[0]:8.0f} {stats[1]:8.0f} {stats[2]:8.0f}")
    devices = {(r["worker"] or {}).get("device") for r in ok}
    cold = sum(1 for r in ok if (r["worker"] or {}).get("coldStart"))
    print(f"\n{len(ok)} completed on {', '.join(sorted(d for d in devices if d))}; {cold} hit a fresh worker process")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=["warm", "cold", "burst"])
    parser.add_argument("--n", type=int, default=20, help="warm: number of sequential requests")
    parser.add_argument("--k", type=int, default=3, help="cold: number of cold requests")
    parser.add_argument("--c", type=int, default=8, help="burst: number of concurrent requests")
    parser.add_argument("--model", default="general", choices=["general", "lite", "matting"])
    parser.add_argument("--transport", default="base64", choices=["base64", "http"], help="how the image reaches the worker")
    parser.add_argument("--outputs", default="mask", help="comma-separated kinds: mask, cutout")
    parser.add_argument("--max-wait", type=float, default=900, help="cold: max seconds to wait for scale-down")
    parser.add_argument("--api-base", help="override the endpoint URL, e.g. http://localhost:8000 for `handler.py --rp_serve_api`")
    args = parser.parse_args()

    endpoint_id, api_key = os.getenv("RUNPOD_ENDPOINT_ID"), os.getenv("RUNPOD_API_KEY")
    if not args.api_base and (not endpoint_id or not api_key):
        sys.exit("Set RUNPOD_ENDPOINT_ID and RUNPOD_API_KEY")
    endpoint = Endpoint(args.api_base or f"{API}/{endpoint_id}", api_key or "local")
    for name in IMAGES:  # fetch before timing anything
        image_bytes(name)

    rows: list[dict] = []
    if args.scenario == "warm":
        print("priming: one untimed request so a worker is up", flush=True)
        endpoint.run(job_input(args, 0))
        for i in range(args.n):
            result, e2e = endpoint.run(job_input(args, i))
            rows.append(record(args, i, result, e2e))
    elif args.scenario == "cold":
        for i in range(args.k):
            print("waiting for the endpoint to scale to zero workers...", flush=True)
            waited = wait_for_zero_workers(endpoint, args.max_wait)
            print(f"  scaled down after {waited:.0f}s; sending", flush=True)
            result, e2e = endpoint.run(job_input(args, i))
            rows.append(record(args, i, result, e2e))
    else:
        inputs = [job_input(args, i) for i in range(args.c)]
        with ThreadPoolExecutor(max_workers=args.c) as pool:
            futures = [pool.submit(endpoint.run, inputs[i]) for i in range(args.c)]
            for i, future in enumerate(futures):
                result, e2e = future.result()
                rows.append(record(args, i, result, e2e))

    summarize(rows)
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS / f"{stamp}-{args.scenario}-{args.model}-{args.transport}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"raw results: {path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
