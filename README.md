# Plant Pal

**Plant Pal** is a small, local-first web app for tracking houseplants: when to water, what you did, and how your collection is doing. It is **single-user** and **self-hosted**—your data stays on a machine you control (a laptop, a home server, or a Raspberry Pi with a browser or kiosk).

The default way to run it is **Docker Compose**. The app is **FastAPI** + **SQLite**; there is no separate database service.

---

## Screens and experience

There is no screenshot gallery in this repository yet. In the app you get:

- **Home (`/`)** — *Today*: plants that need attention (water or a soil check) and an *All plants* section below.
- **My plants (`/plants`)** — grid of everything in your home.
- **Plant detail** — history, care context, logging a watering (with optional backdate), life events (e.g. repot, move), and removing a plant.
- **Add plant (`/add-plant`)** — create a plant from scratch or from a template; optional **photo** upload.
- **Library (`/library`)** — browse and search **care templates** (with categories) and jump into *Add plant* with a template pre-selected.

The landing page can show **local weather** (temperature and a short vibe line) using the browser’s location and the public [Open-Meteo](https://open-meteo.com/) API—**from the client only**; the server does not call out for weather.

---

## Features

- **Care recommendations** from a **drying model** (pot size, light, material, template-based moisture preference) with **watering history** that feeds back into timing. See `ASSUMPTIONS.md` for the exact rules and thresholds.
- **Watering and events** — log waterings, optional backdate, and non-water life events.
- **Care template library** — seeded templates; add plants from the library or build your own.
- **Optional plant photos** — stored under the data directory; resized with Pillow.
- **PWA basics** — web app manifest and service worker (installable / offline-friendly to the extent implemented; see `app/routes/pwa.py`).
- **JSON API** under `/api/*` (e.g. today’s actions, templates, plants, log watered)—see `app/routes/api.py` for routes. The main UI is server-rendered HTML.
- **Ops endpoints** — `GET /healthz` (liveness + DB check) and `GET /status` (version, DB file info, uptime). Omitted from OpenAPI.
- **Security middleware** — configurable host allowlist, optional CSP, sensible default headers (`app/security.py`).

There is **no multi-user accounts or login** in the app: it assumes one household and one browser session model.

---

## Tech stack

| Layer | Choice |
|--------|--------|
| Runtime | Python **3.12** |
| Web | **FastAPI**, **Uvicorn**, **Jinja2** templates, **Tailwind** (via Play CDN in templates) |
| Data | **SQLite** (`plant_panel.db`) |
| Images | **Pillow** (optional uploads) |
| Deploy | **Docker** (multi-stage `Dockerfile`), **Compose** (`compose.yaml`) |
| Dev | **Ruff**, **pytest** — see `Makefile` and `MAINTENANCE.md` |

---

## Quick start (Docker Compose — self-hosted)

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) and **Docker Compose v2** (`docker compose`).

From the directory that contains this repo (where `compose.yaml` and `Dockerfile` live):

```bash
git clone <your-clone-url> plant-pal
cd plant-pal

docker compose build
docker compose up -d
```

- App URL: **`http://127.0.0.1:8000`** on the same machine, or **`http://<host-ip>:8000`** from another device on the LAN.
- Health: `curl -fsS http://127.0.0.1:8000/healthz` — expect HTTP **200** and JSON with `"db": "ok"`.
- Logs: `docker compose logs -f`

The built-in `compose.yaml` tags the local image as **`plant-pal:1.0.0`** and mounts a **named volume** at `/app/data` (see below).

### Docker Hub (prebuilt image)

If you **publish** or **consume** an image on Docker Hub instead of building from the repo, use a **version tag** and **multi-arch** (amd64 + arm64) so the same image runs on a desktop and a 64-bit Raspberry Pi. The maintained workflow and exact commands are in [**`RELEASE.md` → Docker Hub**](RELEASE.md#docker-hub-publish-and-pull), including `compose.hub.example.yaml` for **pull-only** machines (no `build:` in the file).

- **Cloning + local build:** `compose.yaml` (current Quick Start)
- **Pulling from Hub:** `compose.hub.example.yaml` after you set your username and tag

---

## Persistent data / where data lives

Inside the container, everything important is under **`/app/data`**:

| Path | Contents |
|------|------------|
| `/app/data/plant_panel.db` | SQLite database (plants, events, templates cache, etc.) |
| `/app/data/uploads/` | Optional user-uploaded plant images |

Compose maps a **named volume** (key `plantpal_data` in `compose.yaml`) to `/app/data`. Data survives `docker compose up` / `down` / `restart` as long as you **do not** run `docker compose down -v` (which removes named volumes declared in the file and **wipes** app data).

**Second install or new machine:** a **new** empty volume means a **fresh** database and empty uploads on first start—this is the default. Copying or restoring data is a deliberate step; see `BACKUPS.md` and `DEPLOYMENT.md`.

**If you use plant photos**, backups must include **`uploads/`** as well as the database—`scripts/backup-plantpal.sh` copies only `plant_panel.db` by design; `BACKUPS.md` documents copying `uploads` separately.

---

## Raspberry Pi notes

- **Architecture:** build on the Pi with `docker compose build`, or build/push a **linux/arm64** (or multi-arch) image from another machine using the comments in the `Dockerfile` or `scripts/docker-buildx-push.sh`.
- **Kiosk / browser:** the app is a normal website on port **8000**; point a fullscreen browser or tablet at `http://<pi-ip>:8000`. Kiosk autostart, firewall, and TLS are **your** host configuration—this repo does not ship systemd units or a reverse proxy.
- **Optional:** set `PLANTPAL_ALLOWED_HOSTS` in the Compose `environment` to your hostname(s) on the LAN (see `app/security.py`). The default is permissive for local dev and logs a warning if unset.

---

## Updating the app

1. Get the new code (e.g. `git pull`) **or** pull a newer image if you use a registry.
2. Rebuild and recreate the container **without** `-v`:

   ```bash
   docker compose build
   docker compose up -d
   ```

3. Run smoke checks: `GET /healthz`, open `/` in a browser, confirm a known plant still appears after a restart if you have data.

Dependency and image maintenance (locks, `make monthly`, base image) are described in `MAINTENANCE.md`.

---

## Backups

- **Conceptual:** back up the **data directory** in the container, at minimum `plant_panel.db` and, if you use them, **`uploads/`**.
- **Practical:** follow **`BACKUPS.md`** for `docker cp`, stop-then-copy for stricter consistency, **volume name** pitfalls (Docker prefixes volume names), and restore cautions.
- **Helper:** `scripts/backup-plantpal.sh` (running container required) saves a timestamped copy of `plant_panel.db` into `backups/` by default.

---

## Development (local, not production)

For **development** on your own machine you typically use a virtualenv and the lockfiles, **not** the production volume story above.

```bash
make venv
make install-dev    # or: make install  (runtime + tools only)
make dev            # ./run.sh reload — code changes with reload
```

- Local server defaults to **127.0.0.1:8000** via `run.sh` (overridable with `PLANTPAL_HOST` / `PLANTPAL_PORT`).
- Run tests and lint: `make check` (or `make test`, `make lint` separately).
- **Do not** point a long-lived “production” Pi at a dev database on your laptop unless you **intend** to migrate that file; see the environment table in `DEPLOYMENT.md`.

---

## Project status and limitations (v1 self-host)

- **v1** here means: **Docker + SQLite + named volume** is supported and documented; see `RELEASE.md` for a release-oriented checklist. The Python package version in `pyproject.toml` may differ from the **image tag** in `compose.yaml` (e.g. `1.0.0`); `/status` reports the installed package version.
- **No** hosted multi-tenant product, **no** built-in authentication, **no** mobile app in this repo.
- **No** automated CI workflows ship in this repository; quality gates are `make check` and friends locally (`Makefile`).
- **TLS, SSO, and reverse proxy** are not configured in-tree—typical for a LAN Pi; if you expose the app beyond a trusted network, add your own hardening.
- The **drying model** is heuristic, not a substitute for checking your plants in person—see `ASSUMPTIONS.md`.

---

## More documentation

| Document | Purpose |
|----------|---------|
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Compose, ports, start/stop/update, fresh vs migrated install, `down` vs `down -v` |
| [`BACKUPS.md`](BACKUPS.md) | Backup/restore, SQLite and WAL notes, volume naming, uploads |
| [`RELEASE.md`](RELEASE.md) | Versioned image, smoke tests, **Docker Hub** publish and pull, `compose.hub.example.yaml` |
| [`MAINTENANCE.md`](MAINTENANCE.md) | Dependency locks, `make monthly`, logging, health endpoints, Docker base image |
| [`ASSUMPTIONS.md`](ASSUMPTIONS.md) | Drying model rules and parameters |
| [`TESTING.md`](TESTING.md) | How tests use isolated DB paths |

**Scripts (optional):** `scripts/backup-plantpal.sh`, `scripts/build-release-image.sh`, `scripts/docker-buildx-push.sh`, `scripts/restore-plantpal-example.sh` — see comments in each file and `BACKUPS.md`.
