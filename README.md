# runpod-birefnet

A general-purpose, self-hostable [RunPod serverless](https://docs.runpod.io/serverless/overview) worker that
removes image backgrounds with [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) on a GPU and returns the alpha
**mask** and/or the transparent **cutout**. Every job is driven entirely by the request — the model variant
(`general`, `lite`, `matting`), the resolution, the output formats, and **where the image is read from / where
the results are written to** (inline base64, S3, or any HTTP endpoint).

| Path | What it is |
|------|------------|
| [`worker/`](worker) | The RunPod serverless worker (Python + PyTorch). The thing you deploy. |
| [`bench/`](bench) | An end-to-end latency benchmark for a deployed endpoint (cold start, queueing, inference, transport). |

## Deploy the worker

### Option A — use the prebuilt image (recommended)

Each version tag publishes a multi-tag image to the GitHub Container Registry:

```
ghcr.io/hinkolas/runpod-birefnet-worker:0.1.0   # exact version
ghcr.io/hinkolas/runpod-birefnet-worker:0.1     # latest patch of 0.1
ghcr.io/hinkolas/runpod-birefnet-worker:latest  # latest release
```

1. In the RunPod console → **Serverless → New Endpoint**, set the container image to a **pinned version**, e.g.
   `ghcr.io/hinkolas/runpod-birefnet-worker:0.1.0`. Avoid `:latest` in production — it's mutable, so RunPod
   may keep serving a cached older image and your deployments aren't reproducible. Pin a semver tag and bump it
   deliberately to upgrade, or reference the image's `@sha256:…` digest for absolute reproducibility. See RunPod's
   [image versioning guide](https://docs.runpod.io/serverless/workers/deploy#image-versioning).
2. Pick a **GPU** worker (16 GB+ VRAM), allow CUDA 12.6+, and enable FlashBoot.
3. Optionally set `PRELOAD_MODELS` and the `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` env vars.
4. Submit jobs to `https://api.runpod.ai/v2/<ENDPOINT_ID>/runsync` (or `/run`) — see
   [`worker/README.md`](worker/README.md) for the full job schema, storage backends, and response shape.

> **GHCR visibility:** the package is private by default. Either make it public
> (repo → Packages → the image → *Package settings* → *Change visibility*), or add registry pull credentials
> in your RunPod endpoint (username = your GitHub username, password = a PAT with `read:packages`).

### Option B — build it yourself

```sh
docker build --platform linux/amd64 -t runpod-birefnet-worker worker/
```

The image is several GB (the CUDA libraries ship inside the PyTorch wheels) and bakes in the model weights at
pinned revisions. Push it to a registry RunPod can pull and point an endpoint at it.

## Releasing (CI)

Pushing a semver tag builds and publishes the worker image automatically via
[`.github/workflows/worker-image.yml`](.github/workflows/worker-image.yml):

```sh
git tag v0.1.0
git push origin v0.1.0
```

This produces `ghcr.io/hinkolas/runpod-birefnet-worker` tagged `0.1.0`, `0.1`, and `latest`. The workflow
uses the built-in `GITHUB_TOKEN` (no secrets to configure) and builds `linux/amd64` (RunPod's worker arch).

## Measuring latency

See [`bench/README.md`](bench/README.md). In short:

```sh
export RUNPOD_API_KEY=… RUNPOD_ENDPOINT_ID=…
uv run bench/latency.py warm --n 20
uv run bench/latency.py cold --k 3
```

## Models & license

The worker code is [MIT](LICENSE). The BiRefNet weights and model code are by
[Peng Zheng et al.](https://github.com/ZhengPeng7/BiRefNet), also MIT-licensed, and are pulled from Hugging Face
([general](https://huggingface.co/ZhengPeng7/BiRefNet), [lite](https://huggingface.co/ZhengPeng7/BiRefNet_lite),
[matting](https://huggingface.co/ZhengPeng7/BiRefNet-matting)) at build time.
