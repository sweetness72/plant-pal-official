# syntax=docker/dockerfile:1
# Plant Pal — FastAPI + uvicorn. Data: mount a volume on /app/data for SQLite persistence.
#
# Local test (Mac/Linux):
#   docker build -t plant-pal:local .
#   docker run --rm -p 127.0.0.1:8000:8000 -v plantpal-data:/app/data plant-pal:local
#   open http://127.0.0.1:8000
#
# Push for Raspberry Pi (ARM64), from your dev machine:
#   docker buildx create --use   # once per machine, if you have no builder
#   docker buildx build --platform linux/arm64 -t YOUR_REGISTRY/plant-pal:latest --push .
#
# Multi-platform (amd64 + arm64) so one tag works on desktop and Pi:
#   docker buildx build --platform linux/amd64,linux/arm64 -t YOUR_REGISTRY/plant-pal:latest --push .

FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin plantpal

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    PLANTPAL_HOST=0.0.0.0 \
    PLANTPAL_PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

COPY --chown=plantpal:plantpal . .

RUN mkdir -p /app/data && chown plantpal:plantpal /app/data

USER plantpal

EXPOSE 8000

CMD ["sh", "-c", "exec python3 -m uvicorn app:app --host \"${PLANTPAL_HOST}\" --port \"${PLANTPAL_PORT}\""]
