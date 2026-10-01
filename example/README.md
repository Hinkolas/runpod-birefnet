# Background Removal Demo UI

A small SvelteKit app that drives the [`worker/`](../worker) BiRefNet worker using its **inline (base64)
transport**. Drop, paste or pick an image, choose a model / resolution / cutout format, and compare the
cutout against the original with a slider — all with **no database and no public URL**: results live in the
browser tab only.

## How it works

```
Browser ──image bytes──▶ SvelteKit  ──/runsync (base64 in)──▶ RunPod worker
Browser ◀──mask + cutout── SvelteKit ◀──base64 out────────────┘
```

- **Remove** (`POST /api/remove-background?model=…&resolution=…&format=…`) takes the raw image bytes,
  base64-encodes them into the job's `source`, and calls RunPod's `/runsync` with no `destination`, so the
  worker returns a PNG **mask** and a PNG/WebP **cutout** inline.
- If the job outlasts RunPod's sync window (e.g. a cold start), the server falls back to polling `/status`
  until it finishes, and cancels the job if it exceeds `RUNPOD_TIMEOUT_MS`.
- The browser turns the base64 outputs into object URLs for the viewer (compare / cutout / mask / original,
  on a transparent, white or black backdrop) and the download buttons.
- Every run shows the timing split: browser total, RunPod `delayTime` (queue + cold start, flagged when the
  job landed on a fresh worker), `executionTime` (billed compute), and the worker's per-stage `timings`.

Unlike the transcoding demo, the worker never calls back into this server, so there's no
`PUBLIC_BASE_URL` and no tunnel to set up for local development. These jobs are small and fast enough
that inline transport is the simplest fit.

## Configuration

Environment variables (all read at runtime):

| Var                  | Required | Purpose                                                                              |
| -------------------- | -------- | ------------------------------------------------------------------------------------ |
| `RUNPOD_API_KEY`     | yes      | RunPod API key used to submit jobs.                                                  |
| `RUNPOD_ENDPOINT_ID` | yes      | The serverless endpoint running `worker/`.                                           |
| `APP_ID`             | optional | Tags each job's `metadata.app` for usage attribution (default `demo-ui`).            |
| `RUNPOD_TIMEOUT_MS`  | optional | How long to wait for a job, incl. cold start, before cancelling it (default 300000). |
| `BODY_SIZE_LIMIT`    | prod     | adapter-node request body cap. The Dockerfile sets `11M` to fit the 10 MiB limit.    |

## Develop

```sh
bun install
bun run dev
```

Then set the env vars (e.g. in a `.env`) and open the dev server.

## Build & run with Docker

```sh
docker build -t birefnet-demo .
docker run --rm -p 3000:3000 \
  -e RUNPOD_API_KEY=... \
  -e RUNPOD_ENDPOINT_ID=... \
  birefnet-demo
```

## Deploy with skali

[`skali.yaml`](skali.yaml) deploys the same Dockerfile to [skali](https://github.com/Hinkolas/skali). The app is
stateless, so it declares no database or bucket; `/healthz` backs the readiness and liveness probes. Supply the
values per environment (in a `.env` here, or stored with the first deploy):

| Value                | Required | Purpose                                                      |
| -------------------- | -------- | ------------------------------------------------------------ |
| `APP_DOMAIN`         | yes      | The route's domain, e.g. `birefnet.localhost` for local dev. |
| `RUNPOD_API_KEY`     | yes      | As above.                                                    |
| `RUNPOD_ENDPOINT_ID` | yes      | As above.                                                    |
| `APP_ID`             | optional | As above (default `demo-ui`).                                |
| `RUNPOD_TIMEOUT_MS`  | optional | As above (default 300000).                                   |

```sh
skali dev            # local cluster; runs `bun run dev` on this machine behind https://$APP_DOMAIN
skali dev --preview  # local cluster, built from the Dockerfile exactly like a remote deploy
skali deploy         # deploy to the current remote
```

`ORIGIN` is derived from `APP_DOMAIN` (`https://…`), since the app sits behind skali's TLS-terminating edge.

## Notes & limitations (it's a demo)

- Images are capped at 10 MiB: base64 inflates them by ~4/3 and RunPod caps a `/runsync` request at 20 MB.
- Inline images and results pass through RunPod's job payloads (see the worker README's
  [security notes](../worker/README.md#credentials--security)). Use the `http`/`s3` transports for anything
  sensitive.
- Results stay in the tab only; reloading clears them. Options are stored per browser in `localStorage`.
- The mask is always PNG; the format option applies to the cutout (WebP at quality 90 is much smaller for
  large photos).
