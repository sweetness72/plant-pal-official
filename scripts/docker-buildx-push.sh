#!/usr/bin/env bash
# Build and push Plant Pal to a registry (Docker Hub, GHCR, etc.).
#
# Default: multi-arch **amd64 + arm64** (desktop + Raspberry Pi) in one tag.
#
# Prerequisite: `docker login` to your registry (e.g. Docker Hub) once.
#
# Publish a versioned tag (replace YOURUSER and version):
#   export IMAGE=docker.io/YOURUSER/plant-pal:1.0.0
#   ./scripts/docker-buildx-push.sh
#
# Raspberry Pi / arm64 only (smaller CI matrix, not typical for public Hub):
#   PLATFORMS=linux/arm64 ./scripts/docker-buildx-push.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="${IMAGE:?Set IMAGE, e.g. export IMAGE=docker.io/youruser/plant-pal:1.0.0}"
# One manifest for both architectures (Docker Hub "multi-platform" image).
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

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
