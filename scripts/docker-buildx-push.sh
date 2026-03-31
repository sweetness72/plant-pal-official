#!/usr/bin/env bash
# Build and push Plant Pal for Raspberry Pi (or multi-arch).
#
# Usage:
#   export IMAGE=docker.io/YOURUSER/plant-pal:latest
#   ./scripts/docker-buildx-push.sh
#
# ARM64 only (typical Pi 4 / Pi 5):
#   PLATFORMS=linux/arm64 ./scripts/docker-buildx-push.sh
#
# One tag for Mac/PC and Pi:
#   PLATFORMS=linux/amd64,linux/arm64 ./scripts/docker-buildx-push.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="${IMAGE:?Set IMAGE, e.g. export IMAGE=docker.io/youruser/plant-pal:latest}"
PLATFORMS="${PLATFORMS:-linux/arm64}"

if ! docker buildx inspect plantpal-builder >/dev/null 2>&1; then
  docker buildx create --name plantpal-builder --driver docker-container --use
else
  docker buildx use plantpal-builder
fi

docker buildx build \
  --platform "$PLATFORMS" \
  -t "$IMAGE" \
  --push \
  .

echo "Pushed: $IMAGE (platforms: $PLATFORMS)"
