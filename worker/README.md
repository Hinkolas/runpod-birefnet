# Background Removal Worker

A general-purpose [RunPod serverless](https://docs.runpod.io/serverless/overview) worker that removes the
background of an image with [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) and returns an alpha **mask**
and/or the transparent **cutout**.

Everything about a job is driven by the request — the model variant, inference resolution, output kinds and
formats, and **where the image comes from and where the results go**. Storage is pluggable per request: send
the image inline as base64 or point at S3 / any HTTP URL, and get the results back inline or uploaded to S3 /
an HTTP endpoint on your own server. No per-bucket configuration is baked into the worker.

- **GPU** inference in fp16 (PyTorch + CUDA 12.6). The weights of all three models are **baked into the image**,
  so a cold start never downloads anything.
- Three models, selectable per request: `general`, `lite` (faster, rougher edges), and `matting` (soft alpha for
  hair, fur and semi-transparent edges).
- Latency-oriented: models load and warm up before the worker takes jobs, and every response carries a
  per-stage `timings` breakdown plus cold-start info (see [Timings & cold starts](#timings--cold-starts)).

---

## Job input

The RunPod job body is `{ "input": <RemoveBackgroundInput> }`.

### `RemoveBackgroundInput`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `source` | [`Source`](#source-download) | — | Where the image comes from. |
| `destination` | [`Destination`](#destination-upload) | `null` | Where to upload the results. Omit ⇒ results come back **inline** as base64. |
| `model` | `"general"` \| `"lite"` \| `"matting"` | `"general"` | Model variant. Variants not in `PRELOAD_MODELS` load on first use (a few seconds, once per worker). |
| `resolution` | int (256–2048, multiple of 32) | `1024` | Square inference size. BiRefNet is trained at 1024; higher can help fine detail on large images at ~quadratic cost. |
| `outputs` | [`Output`](#output)[] | one PNG `mask` | What to produce. Each (`kind`, `format`) pair at most once. |
| `metadata` | object | `{}` | Free-form passthrough, echoed verbatim in the response. Tag jobs for usage attribution, e.g. `{ "app": "app-a" }`. |

The image's EXIF orientation is applied before inference; outputs always match the (oriented) source size.

### `Output`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `kind` | `"mask"` \| `"cutout"` | `"mask"` | `mask`: 8-bit grayscale alpha (white = foreground). `cutout`: the source as RGBA with the mask as alpha. |
| `format` | `"png"` \| `"webp"` | `"png"` | |
| `quality` | int 1–100 | `90` | webp only; `100` ⇒ lossless. Ignored for png. |

### `Source` (download)

**`base64`** — the image travels inside the request. Lowest latency for small images; mind RunPod's request
size limits for large ones (use `http`/`s3` instead):

| Field | Type | Default |
|-------|------|---------|
| `type` | `"base64"` | — |
| `data` | string | — (raw base64, or a `data:` URL) |

**`http`** — a single streaming GET (works with **presigned URLs**):

| Field | Type | Default |
|-------|------|---------|
| `type` | `"http"` | — |
| `url` | string | — |
| `headers` | object | `{}` |

**`s3`** — boto3 download from any S3-compatible provider (AWS, Hetzner, Cloudflare R2, Backblaze, MinIO, ...):

| Field | Type | Default |
|-------|------|---------|
| `type` | `"s3"` | — |
| `bucket` | string | — |
| `key` | string | — |
| `endpointUrl` | string | `null` (real AWS regional endpoint) |
| `region` | string | `"auto"` |
| `accessKeyId` | string | `null` → env fallback |
| `secretAccessKey` | string | `null` → env fallback |

### `Destination` (upload)

Each output is stored as `<kind>.<format>`, e.g. `mask.png`, `cutout.webp`.

**`s3`** — boto3 upload under a prefix (`<prefix>/mask.png`), with the correct `Content-Type`:

| Field | Type | Default |
|-------|------|---------|
| `type` | `"s3"` | — |
| `bucket` | string | — |
| `prefix` | string | — |
| `endpointUrl` | string | `null` |
| `region` | string | `"auto"` |
| `accessKeyId` | string | `null` → env fallback |
| `secretAccessKey` | string | `null` → env fallback |

**`http`** — one HTTP `PUT` per output file to `{baseUrl}/{fileName}` (e.g. `…/jobs/123/mask.png`), with the
file's `Content-Type` set. Auth is whatever you put in `headers`:

| Field | Type | Default |
|-------|------|---------|
| `type` | `"http"` | — |
| `baseUrl` | string | — |
| `headers` | object | `{}` (e.g. `{"Authorization": "Bearer …"}`) |

---

## Example requests

**Inline in, inline out** (the simplest, lowest-latency call):

```json
{
  "input": {
    "source": { "type": "base64", "data": "<base64 of the image>" }
  }
}
```

**URL in, mask + webp cutout inline, matting model:**

```json
{
  "input": {
    "source": { "type": "http", "url": "https://example.com/portrait.jpg" },
    "model": "matting",
    "outputs": [
      { "kind": "mask", "format": "png" },
      { "kind": "cutout", "format": "webp", "quality": 90 }
    ],
    "metadata": { "app": "app-a", "imageId": "img-42" }
  }
}
```

**S3 in, S3 out** (credentials omitted → uses the worker's env "house account"):

```json
{
  "input": {
    "source": {
      "type": "s3",
      "endpointUrl": "https://fsn1.your-objectstorage.com",
      "bucket": "uploads",
      "key": "originals/img-42.jpg"
    },
    "destination": {
      "type": "s3",
      "endpointUrl": "https://fsn1.your-objectstorage.com",
      "bucket": "uploads",
      "prefix": "processed/img-42"
    },
    "outputs": [{ "kind": "cutout", "format": "png" }]
  }
}
```

**HTTP in, HTTP out** (e.g. an app that keeps files on its own disk):

```json
{
  "input": {
    "source": { "type": "http", "url": "https://app.example.com/api/files/42/source", "headers": { "Authorization": "Bearer …" } },
    "destination": { "type": "http", "baseUrl": "https://app.example.com/api/files/42/output", "headers": { "Authorization": "Bearer …" } }
  }
}
```

---

## Response

```jsonc
{
  "metadata": { "app": "app-a", "imageId": "img-42" },  // echoed from the request
  "model": "general",
  "resolution": 1024,
  "destinationType": "inline",                          // "inline" | "s3" | "http"
  "outputs": [
    {
      "kind": "mask",
      "format": "png",
      "fileName": "mask.png",
      "width": 612,
      "height": 408,
      "bytes": 9942,
      "data": "iVBORw0KGgo…"                            // inline only; "key" for s3, "url" for http
    }
  ],
  "timings": {                                          // ms, measured inside the handler
    "downloadMs": 0.3, "decodeMs": 2.8, "preprocessMs": 9.9, "inferenceMs": 98.1,
    "postprocessMs": 0.6, "encodeMs": 12.4, "uploadMs": 0.0, "totalMs": 125.3
  },
  "worker": {
    "device": "NVIDIA GeForce RTX 4090",
    "dtype": "float16",
    "coldStart": false,       // true on the first job this worker process handles
    "jobIndex": 17,           // jobs handled by this worker process so far
    "startupMs": 9120,        // process start → models loaded and warmed up
    "uptimeMs": 284013,       // since the worker became ready
    "modelLoadMs": null       // set when this job had to load a non-preloaded model
  }
}
```

(The timing values above are illustrative, not measured.)

---

## Timings & cold starts

A request's end-to-end latency is roughly:

```
client e2e ≈ network + RunPod API  +  delayTime (queue + cold start)  +  executionTime (handler)
```

- RunPod reports `delayTime` and `executionTime` on every `/runsync` / `/status` response.
- `timings` breaks `executionTime` down by stage, so transfer costs (`downloadMs`, `uploadMs`) are visible
  separately from `inferenceMs`.
- `worker.coldStart` tells you whether the job landed on a fresh worker process. On a cold job, `delayTime`
  includes the container start plus `worker.startupMs` (loading and warming up the preloaded models).

[`bench/latency.py`](../bench/latency.py) measures all of this against a deployed endpoint.

---

## Credentials & security

The worker holds **no per-bucket configuration**. Credentials for the `s3` backend resolve in this order:

1. `accessKeyId` / `secretAccessKey` in the request's storage config (per-request, any bucket), then
2. `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` env vars, then
3. `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars.

Guidance:

- **Single bucket for everything?** Set the env "house account" once on the endpoint and omit credentials from
  every request.
- **Downloads:** prefer the `http` source with a **presigned GET URL** — no download credentials ever transit
  the job payload.
- **Per-request credentials end up in the RunPod job payload (and likely its logs).** Only put them there for
  genuinely multi-tenant destinations, and prefer scoped / short-lived keys when you do.
- **Inline (base64) images also end up in the job payload.** Use `http`/`s3` for anything sensitive you don't
  want sitting in RunPod's job records.

### Env vars

| Var | Purpose |
|-----|---------|
| `PRELOAD_MODELS` | Comma-separated models to load before taking jobs (default `general`). Others load on first use. Preloading more makes cold starts longer but avoids a first-use stall. |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Optional "house account" for the `s3` backend. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Recognised as a fallback. |

---

## Deploy to RunPod

1. **Serverless → New Endpoint**, container image pinned to a version, e.g.
   `ghcr.io/hinkolas/runpod-birefnet-worker:0.1.0` (see the [root README](../README.md) for tags and GHCR
   visibility).
2. Pick a **GPU** worker. BiRefNet in fp16 needs roughly 4–5 GB of VRAM at 1024px (more at higher
   `resolution`), so any 16 GB+ GPU works; faster GPUs mainly shorten `inferenceMs`.
3. Allow CUDA **12.6 or newer** in the endpoint's CUDA version filter (the image ships CUDA 12.6 wheels).
4. Enable **FlashBoot** — it keeps worker state around after scale-down, which is what makes restarts fast.
5. Choose **idle timeout** / **active workers** by how much latency you're willing to trade for cost: with zero
   active workers, a request after the idle timeout pays a cold start.
6. Optionally set `PRELOAD_MODELS` and the S3 env vars.

### Local testing

Without a GPU (e.g. on a Mac, which uses MPS) straight from source:

```sh
cd worker
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch==2.14.1 torchvision==0.29.1 -r requirements.txt
.venv/bin/python handler.py --test_input test_input.json        # one job, prints the response
.venv/bin/python handler.py --rp_serve_api --rp_api_port 8000   # local /run, /runsync, /status API
```

Locally the models download from Hugging Face on first use (the image has them baked in).

---

## Module layout

| File | Responsibility |
|------|----------------|
| `handler.py` | RunPod entrypoint, orchestration, timings, response shape. |
| `schema.py` | Pydantic request contract. No I/O. |
| `storage.py` | `s3` / `http` / `base64` source and destination backends, credential resolution. |
| `inference.py` | Model registry (pinned revisions), loading + warmup, preprocess → infer → postprocess. |
| `bake_models.py` | Build-time only: downloads and verifies the weights in the image. |
