"""Build-time step: download every model in inference.MODELS into HF_HOME.

Loading each model once (on the CPU, no forward pass) also populates transformers'
remote-code module cache and fails the image build early if a checkpoint or its
code is broken, instead of on the first cold start in production.
"""

from __future__ import annotations

from huggingface_hub import snapshot_download
from transformers import AutoModelForImageSegmentation

from inference import MODELS

for name, (repo, revision) in MODELS.items():
    path = snapshot_download(repo, revision=revision)
    AutoModelForImageSegmentation.from_pretrained(repo, revision=revision, trust_remote_code=True)
    print(f"Baked {name}: {repo}@{revision[:8]} -> {path}", flush=True)
