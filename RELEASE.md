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

## Empty volume vs existing data

| Situation | What you get |
|-----------|----------------|
| **New named volume** (first `docker compose up` on a host) | Empty `data/`. Migrations + seed at startup create a **fresh** DB. Safe for a new Pi or a second device you want empty. |
| **Same named volume, new image** | **Data preserved**. Migrations run on upgrade. This is a normal update. |
| **Volume replaced or deleted** | **Data loss** unless you restored from backup. |
| **Second Pi with a new volume** | **Fresh** app data — correct for a spare unit until you **restore** a copy of `plant_panel.db` (and uploads if used). |

**Rule of thumb:** production data should exist only on the **main** Pi’s volume until you **choose** to copy/restore elsewhere.

## Files to read next

- `DEPLOYMENT.md` — Pi, compose, start/stop/update.
- `BACKUPS.md` — what to back up, restore, and where the DB lives.
- `scripts/` — optional `backup-plantpal.sh` / `restore-plantpal-example.sh`.
