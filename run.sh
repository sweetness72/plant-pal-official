#!/usr/bin/env bash
# Run Plant Pal locally: defaults to 127.0.0.1:8000. Override with PLANTPAL_HOST / PLANTPAL_PORT
# (Dockerfile sets PLANTPAL_HOST=0.0.0.0 so the container accepts connections on the mapped port.)
# Use ./run.sh reload to watch for code changes and auto-restart (excludes .venv and data).
cd "$(dirname "$0")"
HOST="${PLANTPAL_HOST:-127.0.0.1}"
PORT="${PLANTPAL_PORT:-8000}"
if [ -d .venv ]; then
  source .venv/bin/activate
fi
if [ "$1" = "reload" ]; then
  exec python3 -m uvicorn app:app --host "$HOST" --port "$PORT" --reload \
    --reload-exclude '.venv/*' --reload-exclude '.venv/*/*' --reload-exclude '.venv/*/*/*' \
    --reload-exclude 'data/*'
else
  exec python3 -m uvicorn app:app --host "$HOST" --port "$PORT"
fi
