# Latency benchmark

[`latency.py`](latency.py) measures what a caller actually waits for when using a deployed endpoint — not just
the GPU time. Each request is split into:

| Component | Source | What it covers |
|-----------|--------|----------------|
| client end-to-end | measured locally | Everything, from sending the request to having the result. |
| runpod delay | RunPod `delayTime` | Time in the queue, **including a cold start** if no worker was up. |
| runpod execution | RunPod `executionTime` | The handler, from job pickup to return. |
| network + API overhead | e2e − delay − execution | Round trips to `api.runpod.ai`, request/response transfer (incl. base64 payloads). |
| handler stages | the worker's `timings` | download, decode, preprocess, inference, postprocess, encode, upload. |
| worker startup | the worker's `worker.startupMs` | Process start → models loaded and warmed up (only on cold jobs). |

## Running it

Needs [uv](https://docs.astral.sh/uv/) (dependencies are declared inline in the script):

```sh
export RUNPOD_API_KEY=… RUNPOD_ENDPOINT_ID=…

uv run bench/latency.py warm --n 20              # steady state: a worker is already up
uv run bench/latency.py cold --k 3               # after the endpoint scaled to zero
uv run bench/latency.py burst --c 8              # 8 requests at once: queueing + scale-up
uv run bench/latency.py warm --transport http    # image fetched by URL instead of sent inline
uv run bench/latency.py warm --model lite --outputs mask,cutout
```

- **`warm`** sends one untimed priming request first, then N sequential `/runsync` calls.
- **`cold`** polls `/health` until the endpoint reports no workers, then sends a single request, K times. How
  long that wait takes depends on the endpoint's idle timeout. With FlashBoot, a "cold" request may resume a
  retained worker (`coldStart: false`, small `delayTime`) rather than start a fresh one — the output shows which.
- **`burst`** fires C concurrent requests. With fewer workers than requests, later ones queue (higher `delay`).

The test images are seven samples from the
[transformers.js docs dataset](https://huggingface.co/datasets/Xenova/transformers.js-docs), downloaded once into
`bench/.cache/`. Raw per-request results are written to `bench/results/*.jsonl` (both git-ignored), so runs on
different GPU types or settings can be compared later.

To try the client without an endpoint, run the worker's local API (`handler.py --rp_serve_api`, see
[`worker/README.md`](../worker/README.md#local-testing)) and pass `--api-base http://localhost:8000`. The
local server doesn't report `delayTime`/`executionTime`, so only e2e and handler timings are meaningful there.

## Reference: local Apple Silicon

For comparison, the same model (`general`, fp16, 1024px) measured on local Macs, model call only (no
transport, no queue):

| Machine | Backend | Per image |
|---------|---------|-----------|
| M4 Pro (Mac mini) | Core ML, GPU | 554 ms |
| M4 Pro (Mac mini) | PyTorch, MPS | 715 ms |
| M2 Pro (MacBook Pro) | Core ML, GPU | 762 ms |
| M2 Pro (MacBook Pro) | PyTorch, MPS | 1,071 ms |
