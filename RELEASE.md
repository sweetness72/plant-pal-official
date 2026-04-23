# Plant Pal — release checklist (v1)

This document is for **shipping a versioned image** and cutting a **v1** release. It is not a feature spec.

## What “ready for v1” means here

- The app runs in Docker with a **named volume** for `/app/data`.
- You can **build**, **tag**, and **run** a specific image version (e.g. `plant-pal:1.0.0`).
- **Docs** exist for deploy, backup, and restore (see `DEPLOYMENT.md`, `BACKUPS.md`).
- **Production** on the main Pi is **intentional**: real plant data only after hardware is ready; dev laptop stays throwaway.

## Pre-release checklist

- [ ] `make check` (or your CI) passes: tests + lint.
- [ ] `docker compose build` succeeds (see `compose.yaml` image tag).
- [ ] Image tag in `compose.yaml` matches the version you intend to run (bump if needed).
- [ ] `PLANTPAL_ALLOWED_HOSTS` plan for the Pi (if not using default `*` ) — see `MAINTENANCE.md` / `app/security.py`.
- [ ] You know **which machine** is “prod Pi” vs “dev laptop” (see `DEPLOYMENT.md`).

## Smoke test (after `docker compose up -d`)

- [ ] `GET /` returns 200 in a browser (or `curl -fsS http://127.0.0.1:8000/healthz`).
- [ ] `GET /healthz` returns JSON with `"db": "ok"` and HTTP 200 (see `app/routes/health.py`; field is `db`, not `db_status`).
- [ ] Optional: add one throwaway plant, log a watering, confirm it persists **across `docker compose restart`**.

## Image tagging guidance

- **Do not** deploy production with a bare `:latest` if you can avoid it. Prefer an explicit tag that matches your release (e.g. `1.0.0`, `1.0.1`).
- `compose.yaml` pins `image: plant-pal:1.0.0` and `build: .` so `docker compose build` produces that tag locally.
- For a registry (GHCR, Docker Hub, private):

  ```text
  docker build -t YOUR_REGISTRY/plant-pal:1.0.0 .
  docker push YOUR_REGISTRY/plant-pal:1.0.0
  ```

  On the Pi, set `image: YOUR_REGISTRY/plant-pal:1.0.0` and **remove** `build: .` if you only pull prebuilt images.

- Set `PLANTPAL_GIT_SHA` in the container env (optional) so `/status` shows the build; see `Dockerfile` and `app/routes/health.py`.

## Docker Hub (publish and pull)

This is the **single** documented path to publish a **multi-arch** image (amd64 + arm64) so the same tag works on a normal PC and a 64-bit Raspberry Pi.

### Two ways to run the app (do not mix them up)

| | **Local / maintainer (clone + build)** | **Production / user (pull only)** |
|---|----------------------------------------|------------------------------------|
| **You have** | This git repo, `Dockerfile` | A machine with Docker, **no** source (optional) |
| **Compose file** | `compose.yaml` (has `build: .` + local `image:`) | `compose.hub.example.yaml` **or** a copy with `image:` and **no** `build:` |
| **Refresh app** | `git pull` → `docker compose build` → `up -d` | `docker compose pull` → `docker compose up -d` |
| **Image tag** | Built locally, e.g. `plant-pal:1.0.0` | e.g. `docker.io/<username>/plant-pal:1.0.0` on Docker Hub |

### Tagging on Docker Hub

- Prefer **version tags** (`1.0.0`, `1.0.1`), not a bare `latest` only, for production. You may still push `latest` for convenience; keep version tags the source of truth.
- The image name in examples below uses **`YOUR_DOCKERHUB_USER`** — replace with your real Docker Hub username. The full reference is `docker.io/<user>/plant-pal:<tag>`; Docker also accepts the short form `<user>/plant-pal:<tag>`.

### Publish: multi-arch build and push (maintainer, one machine)

1. [Install Docker with Buildx](https://docs.docker.com/build/) (current Docker Desktop / Engine includes it).
2. Log in: `docker login` (use your Docker Hub user when prompted).
3. From the repo root, set the **remote** name and your **version** tag, then run the script:

   ```bash
   export IMAGE=docker.io/YOUR_DOCKERHUB_USER/plant-pal:1.0.0
   ./scripts/docker-buildx-push.sh
   ```

   The script uses **platforms** `linux/amd64,linux/arm64` by default (one manifest, two architectures). It creates a `plantpal-builder` buildx instance if needed, then `buildx build --push`.

4. (Optional) Push a moving tag for testers: re-run with e.g. `export IMAGE=docker.io/YOUR_DOCKERHUB_USER/plant-pal:latest` (still prefer immutable version tags for anything you care about).

5. If `buildx` errors when building a **non-native** platform (e.g. arm64 on an Intel Linux box), enable QEMU / binfmt once as described in Docker’s [multi-platform builds](https://docs.docker.com/build/building/multi-platform/) — Docker Desktop usually does this for you; bare Linux may need a one-time setup.

**Not for publishing multi-arch:** plain `docker build` or `scripts/build-release-image.sh` — those produce a **single** architecture (the host’s). Use them to smoke-test locally, then use `docker-buildx-push.sh` to publish for everyone.

**ARM64 only** (e.g. faster iteration): `PLATFORMS=linux/arm64 ./scripts/docker-buildx-push.sh` (Pi-only image; not ideal for a public “works everywhere” tag).

### After publishing: `compose` for a pull-only host (Pi, VPS, or friend’s machine)

1. Copy `compose.hub.example.yaml` to the server (e.g. as `compose.yaml`).
2. Edit `image:`: replace `YOUR_DOCKERHUB_USER` and bump the tag to match what you pushed (e.g. `1.0.0`).
3. Start **without** building from source:

   ```bash
   docker compose pull
   docker compose up -d
   ```

Or in one line from the repo: `docker compose -f compose.hub.example.yaml up -d` after editing the file in place (still replace the placeholder user).

Data is unchanged: the named volume in the example is still `plantpal_data` → `/app/data` — see `DEPLOYMENT.md` and `BACKUPS.md`.

### Public visibility

Create the repository on Docker Hub as **public** if you want `docker pull` to work for anonymous users; **private** repos need `docker login` on each host.

## Empty volume vs existing data

| Situation | What you get |
|-----------|----------------|
| **New named volume** (first `docker compose up` on a host) | Empty `data/`. Migrations + seed at startup create a **fresh** DB. Safe for a new Pi or a second device you want empty. |
| **Same named volume, new image** | **Data preserved**. Migrations run on upgrade. This is a normal update. |
| **Volume replaced or deleted** | **Data loss** unless you restored from backup. |
| **Second Pi with a new volume** | **Fresh** app data — correct for a spare unit until you **restore** a copy of `plant_panel.db` (and uploads if used). |

**Rule of thumb:** production data should exist only on the **main** Pi’s volume until you **choose** to copy/restore elsewhere.

## Files to read next

- `DEPLOYMENT.md` — Pi, compose, start/stop/update, including published images.
- `BACKUPS.md` — what to back up, restore, and where the DB lives.
- `compose.hub.example.yaml` — copy-paste compose for **pull-only** (Docker Hub) hosts.
- `scripts/` — `docker-buildx-push.sh` (publish), `backup-plantpal.sh` / `restore-plantpal-example.sh` (data).
