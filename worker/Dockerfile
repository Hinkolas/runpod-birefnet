# GPU worker: PyTorch (CUDA 12.6 wheels) with the BiRefNet weights baked in at pinned
# revisions, so cold starts never download anything. Targets RunPod serverless GPU endpoints.
#
# The CUDA runtime ships inside the torch wheels; the host only needs an NVIDIA driver
# new enough for CUDA 12.6. Pick GPUs with "CUDA 12.6+" allowed in the endpoint settings.
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HOME=/models

WORKDIR /app

# Largest layer first and on its own, so code changes don't invalidate it.
RUN python3 -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu126

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

# Bake the weights (and the models' remote code) into the image.
COPY inference.py bake_models.py ./
RUN python3 bake_models.py && rm bake_models.py

# Never reach out to Hugging Face at runtime.
ENV HF_HUB_OFFLINE=1
# Comma-separated models to load before taking jobs; others load on first use.
ENV PRELOAD_MODELS=general

COPY handler.py schema.py storage.py ./

CMD ["python3", "-u", "handler.py"]
