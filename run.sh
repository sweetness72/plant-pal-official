#!/usr/bin/env bash
# Run Plant Pal locally: defaults to 127.0.0.1:8000. Override with PLANTPAL_HOST / PLANTPAL_PORT
# (Dockerfile sets PLANTPAL_HOST=0.0.0.0 so the container accepts connections on the mapped port.)
# Use ./run.sh reload to watch for code changes and auto-restart.
#
# Reload strategy: whitelist only our source directories. Using --reload-exclude
# against .venv doesn't work reliably because watchfiles walks every subtree
# first and the exclude globs only match specific depths. Explicit
# --reload-dir lists are both faster (smaller tree) and correct by construction.
cd "$(dirname "$0")"
HOST="${PLANTPAL_HOST:-127.0.0.1}"
PORT="${PLANTPAL_PORT:-8000}"
if [ -d .venv ]; then
  source .venv/bin/activate
fi
# --no-server-header: drop the leaky "Server: uvicorn" header. Matches the
# stance in app/security.py (our middleware can't reliably strip this one).
if [ "$1" = "reload" ]; then
  exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload \
    --reload-dir app --reload-dir core --no-server-header
else
  exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --no-server-header
fi
