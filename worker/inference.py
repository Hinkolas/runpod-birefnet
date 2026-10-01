"""BiRefNet model registry and inference.

Models are loaded once per worker process and kept on the device, so only the first
job that needs a given variant pays its load time. `preload()` runs at import time of
handler.py (outside the job loop) for the variants named in `PRELOAD_MODELS`.

The weights are baked into the image at pinned revisions (see Dockerfile), and the
worker runs with HF_HUB_OFFLINE=1, so nothing is fetched at runtime.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoModelForImageSegmentation

# name -> (Hugging Face repo, pinned revision). Keep in sync with the Dockerfile.
MODELS: dict[str, tuple[str, str]] = {
    "general": ("ZhengPeng7/BiRefNet", "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"),
    "lite": ("ZhengPeng7/BiRefNet_lite", "aa62cd87eafb9cc43056d08ef3615a14628b831d"),
    "matting": ("ZhengPeng7/BiRefNet-matting", "eccde0a8cbdce7ac5fecfeb06340fe7b949e85d9"),
}

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def _pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():  # local testing on Apple Silicon
        return torch.device("mps")
    return torch.device("cpu")


DEVICE = _pick_device()
# fp16 halves memory and is ~free in quality for BiRefNet; CPU has no fast fp16 path.
DTYPE = torch.float32 if DEVICE.type == "cpu" else torch.float16

if DEVICE.type == "cuda":
    torch.backends.cudnn.benchmark = True  # input size is fixed per resolution

_models: dict[str, torch.nn.Module] = {}
_lock = threading.Lock()


def device_name() -> str:
    if DEVICE.type == "cuda":
        return torch.cuda.get_device_name(DEVICE)
    return DEVICE.type


def sync() -> None:
    if DEVICE.type == "cuda":
        torch.cuda.synchronize()
    elif DEVICE.type == "mps":
        torch.mps.synchronize()


def get_model(name: str) -> tuple[torch.nn.Module, float | None]:
    """Return the model and, if it had to be loaded by this call, the load time in ms."""
    with _lock:
        if name in _models:
            return _models[name], None
        started = time.perf_counter()
        repo, revision = MODELS[name]
        # Pin the dtype: transformers v5 otherwise keeps the checkpoint's dtype.
        model = AutoModelForImageSegmentation.from_pretrained(
            repo, revision=revision, trust_remote_code=True, dtype=DTYPE
        )
        model = model.to(DEVICE).eval()
        # The first pass compiles kernels / runs cuDNN autotuning; keep it out of real jobs.
        # Going through predict_mask also warms the pre/postprocessing kernels.
        predict_mask(Image.new("RGB", (64, 64)), model, 1024)
        _models[name] = model
        load_ms = (time.perf_counter() - started) * 1000
        print(f"Loaded {name} ({repo}@{revision[:8]}) on {device_name()} in {load_ms:.0f} ms", flush=True)
        return model, load_ms


def preload(names: list[str]) -> None:
    for name in names:
        if name not in MODELS:
            raise ValueError(f"Unknown model in PRELOAD_MODELS: {name!r} (expected one of {list(MODELS)})")
        get_model(name)


@torch.inference_mode()
def predict_mask(image: Image.Image, model: torch.nn.Module, resolution: int) -> tuple[np.ndarray, dict[str, float]]:
    """Run BiRefNet on an RGB image. Returns a uint8 HxW mask at the image's size, plus timings."""
    timings: dict[str, float] = {}

    started = time.perf_counter()
    # Resize with PIL like upstream BiRefNet: its 8-bit rounding of the resized image
    # matters, as a float resize on the device flips ambiguous regions on some images.
    # It also means only the small resized image is copied to the device.
    resized = np.array(image.resize((resolution, resolution), Image.BILINEAR))
    x = torch.from_numpy(resized).to(DEVICE).permute(2, 0, 1)[None].float() / 255
    mean = torch.tensor(MEAN, device=DEVICE).view(1, 3, 1, 1)
    std = torch.tensor(STD, device=DEVICE).view(1, 3, 1, 1)
    x = ((x - mean) / std).to(DTYPE)
    sync()
    timings["preprocessMs"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    pred = model(x)[-1].sigmoid()
    sync()
    timings["inferenceMs"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    pred = F.interpolate(pred.float(), size=(image.height, image.width), mode="bilinear", align_corners=False)
    mask = (pred[0, 0].clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
    timings["postprocessMs"] = (time.perf_counter() - started) * 1000
    return mask, timings
