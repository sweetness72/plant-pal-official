#!/usr/bin/env bash
# Back up plant_panel.db from a running Plant Pal container (Docker Compose).
# Usage: ./scripts/backup-plantpal.sh [output-file.db]
# Env: COMPOSE_FILE (default compose.yaml), PLANTPAL_SERVICE (default plant-pal)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml}"
SERVICE="${PLANTPAL_SERVICE:-plant-pal}"
OUT="${1:-backups/plantpal-$(date +%Y%m%d-%H%M%S).db}"
mkdir -p "$(dirname "$OUT")"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

CID="$(docker compose -f "$COMPOSE_FILE" ps -q "$SERVICE" 2>/dev/null || true)"
if [ -z "${CID:-}" ]; then
  echo "error: no running container for service '$SERVICE'. Start with: docker compose up -d" >&2
  exit 1
fi

docker cp "$CID:/app/data/plant_panel.db" "$OUT_ABS"
echo "Wrote $OUT_ABS"
