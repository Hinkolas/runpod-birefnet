"""RunPod serverless worker: remove the background of an image with BiRefNet.

The whole job is driven by the request `input` (see schema.py): the model variant,
inference resolution and requested outputs (mask and/or RGBA cutout, png/webp) are
request-configurable, and the image source / result destination are pluggable per
request (s3, http, or inline base64).

Latency-oriented: models load and warm up before the worker starts taking jobs, and
every response carries a per-stage `timings` breakdown plus `worker` info (cold start,
startup time), so callers can tell inference apart from transfer and cold-start costs.
Unlike the transcoding worker there are no progress updates: each one is an extra
round trip to RunPod, which would cost more than most whole jobs here.
"""

from __future__ import annotations

import time

PROCESS_STARTED = time.time()

import base64
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import runpod
from PIL import Image, ImageOps
from pydantic import ValidationError

import inference
from schema import Output, RemoveBackgroundInput
from storage import make_destination, make_source

PRELOAD_MODELS = [m.strip() for m in os.getenv("PRELOAD_MODELS", "general").split(",") if m.strip()]


def warm_codecs() -> None:
    """PIL loads its codecs lazily; the first decode/encode costs tens of ms otherwise."""
    for fmt in ("JPEG", "PNG", "WEBP"):
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64)).save(buffer, format=fmt)
        Image.open(buffer).convert("RGBA").save(io.BytesIO(), format=fmt if fmt != "JPEG" else "PNG")


warm_codecs()
inference.preload(PRELOAD_MODELS)
READY_AT = time.time()
print(f"Worker ready in {(READY_AT - PROCESS_STARTED) * 1000:.0f} ms (preloaded: {PRELOAD_MODELS})", flush=True)

_job_count = 0


def encode(image: Image.Image, output: Output) -> bytes:
    buffer = io.BytesIO()
    if output.format == "png":
        # Level 3 is far faster than the default 6 for large images, at a slightly bigger file.
        image.save(buffer, format="PNG", compress_level=3)
    else:
        image.save(buffer, format="WEBP", quality=output.quality, lossless=output.quality == 100)
    return buffer.getvalue()


def ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def handle_remove_background(job: dict[str, Any]) -> dict[str, Any]:
    global _job_count
    _job_count += 1
    job_started = time.perf_counter()
    timings: dict[str, float] = {}

    try:
        payload = RemoveBackgroundInput.model_validate(job.get("input") or {})
    except ValidationError as error:
        raise ValueError(error.json()) from error

    source = make_source(payload.source)
    destination = make_destination(payload.destination) if payload.destination else None
    model, load_ms = inference.get_model(payload.model)

    with tempfile.TemporaryDirectory(prefix="runpod-birefnet-") as tmp:
        temp_dir = Path(tmp)
        source_path = temp_dir / "source"
        output_dir = temp_dir / "out"
        output_dir.mkdir()

        started = time.perf_counter()
        source.download(source_path)
        timings["downloadMs"] = ms_since(started)

        started = time.perf_counter()
        with Image.open(source_path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        timings["decodeMs"] = ms_since(started)

        mask, model_timings = inference.predict_mask(image, model, payload.resolution)
        timings.update({k: round(v, 1) for k, v in model_timings.items()})

        started = time.perf_counter()
        mask_image = Image.fromarray(mask, mode="L")
        files: list[tuple[Output, str, bytes]] = []
        for output in payload.outputs:
            if output.kind == "mask":
                result = mask_image
            else:
                result = image.copy()
                result.putalpha(mask_image)
            data = encode(result, output)
            file_name = f"{output.kind}.{output.format}"
            (output_dir / file_name).write_bytes(data)
            files.append((output, file_name, data))
        timings["encodeMs"] = ms_since(started)

        started = time.perf_counter()
        locations: dict[str, str] = {}
        if destination is not None:
            locations = {item.relativePath: item.location for item in destination.upload(output_dir)}
        timings["uploadMs"] = ms_since(started)

    outputs = []
    for output, file_name, data in files:
        entry: dict[str, Any] = {
            "kind": output.kind,
            "format": output.format,
            "fileName": file_name,
            "width": image.width,
            "height": image.height,
            "bytes": len(data),
        }
        if destination is None:
            entry["data"] = base64.b64encode(data).decode("ascii")
        elif payload.destination.type == "s3":
            entry["key"] = locations[file_name]
        else:
            entry["url"] = locations[file_name]
        outputs.append(entry)

    timings["totalMs"] = ms_since(job_started)
    return {
        "metadata": payload.metadata,
        "model": payload.model,
        "resolution": payload.resolution,
        "destinationType": payload.destination.type if payload.destination else "inline",
        "outputs": outputs,
        "timings": timings,
        "worker": {
            "device": inference.device_name(),
            "dtype": str(inference.DTYPE).removeprefix("torch."),
            "coldStart": _job_count == 1,
            "jobIndex": _job_count,
            "startupMs": round((READY_AT - PROCESS_STARTED) * 1000),
            "uptimeMs": round((time.time() - READY_AT) * 1000),
            # Set when this job had to load a model that wasn't preloaded.
            "modelLoadMs": round(load_ms) if load_ms is not None else None,
        },
    }


def handler(job: dict[str, Any]) -> dict[str, Any]:
    return handle_remove_background(job)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--test_input":
        with open(sys.argv[2], "r", encoding="utf-8") as file:
            test_job = json.load(file)
        print(json.dumps(handler(test_job), indent=2))
    else:
        runpod.serverless.start({"handler": handler})
