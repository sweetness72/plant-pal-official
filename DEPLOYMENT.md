# Plant Pal — deployment (Docker, Raspberry Pi, kiosk)

Conservative, self-hosted setup: **Docker Compose** + **SQLite** on a **named volume**. No external database.

## Environments (do not mix them up)

| | **Dev (laptop)** | **Production (main Pi)** | **Second Pi / spare** |
|---|------------------|----------------------------|------------------------|
| **Purpose** | Develop, test, fake data | Kiosk + real plants | Fresh install or cold spare |
| **Data** | Safe to delete / reset | **Persistent named volume** — back it up | **New volume = empty app** until you **restore** |
| **Real plant data** | Only if you choose (usually avoid) | **Start only when hardware is ready** | Only after **copy/restore** if you want a clone |

**Default rule:** do not copy production `plant_panel.db` to a second device **unless** you mean to duplicate or migrate data. A new Pi with a new volume should get a **fresh** DB for v1 until you decide otherwise.

## What gets persisted

Inside the container, `DATA_DIR` is `/app/data` (see `core/db/connection.py`, `Dockerfile`).

- **SQLite database:** `/app/data/plant_panel.db`
- **User uploads (optional plant photos):** `/app/data/uploads/`

The Compose file mounts a **named volume** to `/app/data` so data survives container recreation.

## Prerequisites on the Pi

- Docker Engine + Docker Compose plugin (v2: `docker compose`).

## Deploy with `compose.yaml`

From the directory that contains `compose.yaml` and the `Dockerfile` (this repo):

```bash
# Build the versioned image (tag must match `image:` in compose.yaml)
docker compose build

# Start in the background
docker compose up -d

# Follow logs
docker compose logs -f
```

- App listens on **port 8000** (mapped to host `8000`). Open `http://<pi-ip>:8000` from a browser on the LAN (or the kiosk).
- **Health:** `http://<pi-ip>:8000/healthz` (image `HEALTHCHECK` in `Dockerfile` applies under Compose too; see `compose.yaml` comments).

## Using a published image (Docker Hub)

For hosts that only **pull** an image (no `git clone`, no `docker compose build`):

- Use `compose.hub.example.yaml` as a template: set `image: docker.io/<your-username>/plant-pal:<tag>`, and **do not** add a `build:` key.
- Run: `docker compose pull` and `docker compose up -d` (same data rules as the table below).

Full tagging and multi-arch publishing steps: **`RELEASE.md` → "Docker Hub"**. That path produces **amd64 + arm64** so the same tag runs on a PC and a 64-bit Raspberry Pi.

**Repo `compose.yaml`** (with `build: .`) stays the default for **cloning this repository** and building locally; it is not required on a machine that only pulls.

## Start / stop / update — which commands keep data

**Your SQLite and uploads live in a Docker named volume** (`plantpal_data` in `compose.yaml`; the *full* volume name on disk is **Compose-prefixed** — see `BACKUPS.md`).

| Command | Containers | **Named app volume / data** |
|--------|------------|----------------------------|
| `docker compose stop` | Stopped, still defined | **Preserved** (volume untouched) |
| `docker compose down` | Removed | **Preserved** — this is the normal default. **No `-v`**. |
| `docker compose down -v` | Removed | **Destroyed** — **deletes** named volumes declared in this compose file, i.e. **wipes app data**. Use **only** when you intentionally want a **fresh** database/uploads. |
| `docker compose restart` / `up -d` after build | Replaced/recreated as needed | **Preserved** (same volume reattached) |

**Safe updates** (new image, same data): `docker compose build` then `docker compose up -d` — or `pull` + `up -d` if using a registry image. Do **not** pass `-v` unless you mean to delete data.

```bash
# Update after pulling new code or changing the image tag
docker compose build
docker compose up -d
```

**Update with no code on the Pi:** set `image:` to your registry tag, then:

```bash
docker compose pull
docker compose up -d
```

## Production data “starts on the real device”

- **Do not** seed the production Pi with test data from your laptop unless you **intend** to carry that DB over (export volume or copy `plant_panel.db`).
- For v1, the intended story is: **first boot on the real Pi** with an **empty volume** → empty DB → you add real plants when the physical setup is ready.
- If you already experimented on a dev container, use a **new volume** on production or **delete** the test data before go-live (see `BACKUPS.md` for file locations).

## Fresh install vs migrated install

| Scenario | Steps |
|----------|--------|
| **Fresh install** | New host or new volume → `docker compose up -d` → empty DB, migrations run at startup. |
| **Same Pi, app update** | `docker compose build` or `pull` → `docker compose up -d` → **same volume**, data kept. |
| **Move to a new Pi** | Install Docker, copy **backup** of `plant_panel.db` (and `uploads/` if needed) per `BACKUPS.md`, or attach a restored volume. Do **not** assume volumes are portable by name across hosts — use **file backup/restore**. |
| **Second Pi as clone** | Only if you **restore** a backup; otherwise treat as **fresh** with its own empty volume. |

## ARM (Raspberry Pi) images

- Build on the Pi: `docker compose build` (native `linux/arm64` on 64-bit Pi OS).
- Or build and push a multi-arch image from CI or `docker buildx` (see comments in `Dockerfile`).

## Environment variables (optional)

Common production tunables (details in `MAINTENANCE.md`):

- `PLANTPAL_ALLOWED_HOSTS` — restrict `Host` header (recommended on a LAN with a known hostname).
- `PLANTPAL_LOG_LEVEL` — default `INFO`; `WARNING` for quieter logs.
- `PLANTPAL_GIT_SHA` — optional, for `/status`.

Set them under `environment:` in `compose.yaml` or use an `env_file` (not committed with secrets).

## Related

- `BACKUPS.md` — backup/restore.
- `RELEASE.md` — release and tagging.
- `Dockerfile` — build details and local `docker run` example.
