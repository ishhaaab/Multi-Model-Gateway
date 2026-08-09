FROM python:3.11-slim AS base

# Prefer IPv4 when resolving host.docker.internal. Docker Desktop also publishes
# an IPv6 host-gateway that isn't routable from the container, and glibc otherwise
# tries it first — causing "Network is unreachable" on host calls to LM Studio /
# ComfyUI. This precedence rule makes IPv4(-mapped) addresses win.
RUN echo 'precedence ::ffff:0:0/96 100' >> /etc/gai.conf

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Development: hot-reload. Running as root is fine on a local / tailnet box.
FROM base AS dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production: unprivileged user, no reload. Used by the prod compose override.
FROM base AS prod
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Image-LoRA training worker (ai-toolkit); GPU required. Inherits the app code
# and backend/requirements.txt from base, then clones ai-toolkit OUTSIDE /app
# (it survives the ./backend:/app bind mount used by compose).
FROM base AS trainer
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
# ai-toolkit's requirements.txt deliberately omits torch (the README has you
# install it first); install the CUDA build the repo pins, then its other deps.
# Version pins verified against PyPI (latest stable, Aug 2026):
#   torch 2.13.0, torchvision 0.28.0, torchaudio 2.11.0
# All three ship cp311 wheels on the cu130 index, so the python:3.11-slim base
# resolves them directly.
RUN git clone --depth 1 https://github.com/ostris/ai-toolkit /opt/ai-toolkit \
    && pip install --no-cache-dir torch==2.13.0 torchvision==0.28.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130 \
    && pip install --no-cache-dir -r /opt/ai-toolkit/requirements.txt
CMD ["arq", "app.trainer_worker.WorkerSettings"]
