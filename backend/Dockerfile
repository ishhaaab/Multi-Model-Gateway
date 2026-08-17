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
