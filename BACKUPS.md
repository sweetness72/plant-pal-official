# Plant Pal — backups and restore (SQLite)

**What matters:** the files under the app’s **data directory** in the container: **`/app/data`**.

| Path (in container) | Contents |
|---------------------|----------|
| `/app/data/plant_panel.db` | **SQLite** — all plants, waterings, templates cache, etc. |
| `/app/data/uploads/` | **Optional** user-uploaded plant images (if used) |

A Compose **named volume** is mounted at `/app/data` (see `compose.yaml`). The **logical** name in the file is `plantpal_data`, but Docker stores it as **`<compose_project>_<volume_name>`** (e.g. `plantpal_plantpal_data`). **Always confirm the real name** before a restore (see below).

## SQLite: hot copy vs stop first (honest, small self-host)

- For a **low-traffic** single-user app, copying `plant_panel.db` **while the app is running** is **often** acceptable in practice.
- SQLite may use **WAL** mode; in that case the main file can have companion `-wal` / `-shm` files. Copying **only** `plant_panel.db` **may not** be a fully consistent snapshot in all edge cases.
- **Conservative recommendation:** `docker compose stop plant-pal`, then copy the DB, then `docker compose start plant-pal` — same as “Option B” below. **Easiest “good enough” for v1 on a Pi.**

## Simple manual backup (recommended to start)

### Option A — `docker cp` (container running)

```bash
# From the directory with compose.yaml; adjust service name if you changed it
mkdir -p backups
CID=$(docker compose ps -q plant-pal)
docker cp "$CID:/app/data/plant_panel.db" "backups/plantpal-$(date +%Y%m%d-%H%M%S).db"
```

### Option B — stop, then copy (stricter, recommended for peace of mind)

```bash
docker compose stop plant-pal
mkdir -p backups
CID=$(docker compose ps -a -q plant-pal)
# If CID is empty you used `docker compose down` (container removed) — use Option A with the stack running, or `docker compose up -d` first to recreate the container.
docker cp "$CID:/app/data/plant_panel.db" "backups/plantpal-$(date +%Y%m%d-%H%M%S).db"
docker compose start plant-pal
```

### Uploads

If you use photos (run after you have a `CID` as above):

```bash
docker cp "$CID:/app/data/uploads" "backups/uploads-$(date +%Y%m%d)"
```

Or only back up `plant_panel.db` if you do not use custom photos.

## Helper script

See `scripts/backup-plantpal.sh` — wraps `docker cp` with a timestamped filename (requires a **running** container).

## Restore (replace DB on the volume) — **verify volume name first**

**You can overwrite the wrong volume** if you guess a name. A **new** empty volume + a “successful” `cp` can look like a restore worked when you actually wrote to a **throwaway** volume.

**Required before any `docker run -v …` restore:**

1. **List volumes** (on the same machine / same project you use in production):

   ```bash
   docker volume ls
   ```

2. **Identify the production volume** for this app. It is **not** literally `plantpal_data` in the first column — it is usually **`<project>_<key>`** where `<key>` comes from the `volumes:` key in `compose.yaml` (e.g. `plantpal_data` → might appear as `plantpal_plantpal_data`).

3. **Double-check** with (replace with the name you see):

   ```bash
   docker volume inspect PASTE_EXACT_NAME
   ```

   Confirm it is the one used by this compose project (same host, not a test stack).

4. **Set a variable** and use it in the command — **no generic placeholder**:

   ```bash
   export PLANTPAL_DATA_VOLUME="PASTE_EXACT_NAME_FROM_docker_volume_ls"
   ```

5. **Then** run the restore (example — adjust backup filename):

   ```bash
   docker compose stop plant-pal
   docker run --rm \
     -v "$PLANTPAL_DATA_VOLUME:/data" \
     -v "$(pwd)/backups:/restore:ro" \
     alpine sh -c 'cp /restore/plantpal-YYYYMMDD-HHMMSS.db /data/plant_panel.db && chown 1000:1000 /data/plant_panel.db'
   docker compose start plant-pal
   ```

**Warning:** this overwrites the live database. Back up the current `plant_panel.db` first if it contains anything you care about.

The app runs as **UID 1000** (`plantpal` in the `Dockerfile`); `chown` keeps permissions sane.

If you restored `uploads/`, copy that tree into `/data/uploads/` using the **same** `$PLANTPAL_DATA_VOLUME` mount.

**Verify after restore:** open the app; `GET /healthz` should return `"db": "ok"`; check `/status` and your plant list.

## Example restore template

`scripts/restore-plantpal-example.sh` — short pointer; follow the steps **above**, not a hard-coded volume name.

## Automation (later)

- `cron` on the Pi: nightly `backup-plantpal.sh` to an external disk or NAS.
- **Off-site:** copy the dated `.db` files only (small).
- **Before upgrades:** always take one backup (see `RELEASE.md`).

## What not to rely on

- **Copying the raw Docker volume directory** from `/var/lib/docker/...` by hand is fragile; prefer `docker cp` or the verified-volume restore flow above.
- **Restoring a DB from a very old schema:** startup runs migrations, but test in a throwaway container if unsure.

## Related

- `DEPLOYMENT.md` — where data lives; `down` vs `down -v`.
- `core/db/connection.py` — `DB_PATH` / `DATA_DIR`.
