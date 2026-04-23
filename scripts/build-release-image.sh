#!/usr/bin/env bash
# Local single-platform `docker build` — fast smoke test; same arch as the host.
# For publishing **multi-arch** (amd64+arm64) to Docker Hub, use scripts/docker-buildx-push.sh.
# Usage: from repo root, ./scripts/build-release-image.sh [tag]
# Example: ./scripts/build-release-image.sh 1.0.1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TAG="${1:-1.0.0}"
NAME="${PLANTPAL_IMAGE_NAME:-plant-pal}"
echo "Building ${NAME}:${TAG}"
docker build -t "${NAME}:${TAG}" .
echo "Done. Update compose.yaml image: line to ${NAME}:${TAG} if you changed the tag."
