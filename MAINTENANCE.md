# Maintenance

Plant Pal is a small, self-hosted, single-user app. The goal of this document
is to keep it that way: reproducible builds, predictable upgrades, and a
five-minute monthly routine that catches drift before it becomes work.

When there is a project README, fold the **Monthly checklist** section below
into it.

---

## Dependency model

| File | Purpose | Edited by |
|---|---|---|
| `requirements.in` | runtime deps, loose version ranges | humans |
| `requirements-dev.in` | dev-only deps, constrained against the runtime lock | humans |
| `requirements.lock` | fully pinned, hash-verified runtime graph | `pip-compile` |
| `requirements-dev.lock` | fully pinned dev graph | `pip-compile` |
| `requirements-tools.txt` | bootstrap (`pip-tools`, `pip-audit`); not shipped | humans, rarely |

Rules of thumb:

- Only edit `.in` files by hand. The `.lock` files are generated.
- Everything (venv, Docker, future CI) installs from `.lock` with
  `--require-hashes`. A drifted or tampered wheel fails the install instead
  of silently producing a different build.
- Dev deps are compiled *against* the runtime lock, so a shared package can
  never have two different pinned versions.

## Daily workflow

```bash
make install-dev     # one-time setup
make dev             # run with autoreload
make check           # lint + format check + tests (pre-push)
```

Adding or removing a dependency:

```bash
# 1. edit requirements.in (or requirements-dev.in)
make lock            # regenerate both lock files
make sync            # prune the venv to match
git add requirements*.in requirements*.lock
```

## Monthly checklist

Five minutes, once a month. Do it on the first of the month so it's easy
to remember.

```bash
make monthly                     # upgrade + sync + audit + check in one shot
git diff requirements*.lock      # eyeball the diff
make docker && docker run ...    # rebuild the image and smoke-test
```

`make monthly` is the consolidated routine — it runs `upgrade`, `sync`,
`audit`, and `check` and stops if any step fails. Inspect the lock diff
before committing; reject surprising major-version jumps unless the
release notes are reassuring.

If `make audit` reports a vulnerability outside the monthly cycle, patch just
that one package:

```bash
.venv/bin/pip-compile --upgrade-package <name> --generate-hashes \
    --strip-extras --output-file=requirements.lock requirements.in
make sync && make audit && make check
```

Reject surprising major-version jumps unless the release notes are
reassuring. When `pip-audit` flags a CVE that is fixed in a newer release,
upgrade that package specifically as above.

## Docker

The runtime image installs from `requirements.lock --require-hashes`, so the
image is identical on every rebuild given the same lock. Base image is
`python:3.12-slim-bookworm`; OS patches come in by rebuilding the image —
tags move over time even when the tag string is unchanged. Rebuild monthly
as part of the checklist above.

The container has a `HEALTHCHECK` that polls `/healthz` every 30 seconds.
Three consecutive failures mark the container unhealthy, which the Pi's
supervisor (systemd, Docker Compose `restart: unless-stopped`, etc.) can
react to. The probe hits `/healthz`, not `/`, so a cosmetic template
change won't flap it.

### Pinning the base image by digest (optional)

Tags drift — `python:3.12-slim-bookworm` today is not the same bytes as
tomorrow. For strict reproducibility:

```bash
make docker-pin-base
# prints something like: sha256:abcd1234...
```

Paste the digest into the `Dockerfile` (`FROM python:3.12-slim-bookworm@sha256:abcd1234...`).
Refresh it roughly quarterly to keep picking up OS patches. We don't pin
by default because routine monthly rebuilds should pick up OS patches;
digest pinning trades patching-by-default for reproducibility.

## Observability (self-hosted, no Prometheus)

Everything goes to **stdout** — `docker logs` / `journald` on the Pi. No
sidecar, no external SaaS.

### Endpoints

| Path | Role |
|------|------|
| `GET /healthz` | **Liveness / readiness** for Docker `HEALTHCHECK` and process supervisors. Cheap: `SELECT 1` on SQLite. Returns **503** if the DB file cannot be opened. |
| `GET /status` | **Runtime snapshot** (app version, Python, platform, uptime, DB file name + size, `PRAGMA user_version`, current log level). Handy for humans and ad-hoc scripts; not a high-frequency probe. |

Both routes are **omitted from OpenAPI** so they do not clutter the
public API schema.

### Logging environment variables

| Env var | Default | Purpose |
|--------|---------|---------|
| `PLANTPAL_LOG_LEVEL` | `INFO` | Root, `app`, and `core` loggers. Use **`DEBUG`** on your laptop when you need per-plant recommendation lines (`core.drying_model` at DEBUG). **`WARNING`** in production is fine if you only care about errors and migration banners are too chatty. |
| `PLANTPAL_LOG_FORMAT` | `text` | Set to **`json`** for one JSON object per line (easier to pipe through `jq` if you later add a log shipper). |

**Guidance — dev vs production**

- **Local / dev:** `PLANTPAL_LOG_LEVEL=DEBUG` to see `recommendation …` debug lines, migration INFO when they run, and plant action INFO lines. `uvicorn` access logs stay at WARNING unless the root level is DEBUG (then access logs match).
- **Pi / production:** `PLANTPAL_LOG_LEVEL=INFO` (default). You still get startup/shutdown, DB init, migrations when applied, plant add/water/event/remove, and unhandled 500s with a stack trace. **Recommendation** detail is DEBUG-only so a single home page load does not print one line per plant.
- **Quiet prod:** `PLANTPAL_LOG_LEVEL=WARNING` — only warnings and errors; you lose the structured plant-action lines until you bump the level for a troubleshooting session.

Optional: set `PLANTPAL_GIT_SHA` in the container env (e.g. from your CI
build) so `/status` can echo a short commit id for “which image is this?”

### Unhandled errors

The app registers a **last-resort** handler for uncaught exceptions: one
`ERROR` log with a full traceback, response body `{"detail": "Internal server
error"}`. Normal **HTTP 4xx** (e.g. validation) are **not** logged at ERROR.

### SQLite backup and integrity

The database file is `plant_panel.db` under your **data directory** (in
Docker: mount a volume on `/app/data`).

**Integrity check (read-only, safe on a live file for SQLite’s purposes):**

```bash
# Host path or inside the container
sqlite3 /path/to/data/plant_panel.db "PRAGMA integrity_check;"
```

Expect a single line `ok`. Anything else is a sign you should restore
from backup and investigate disk / power-loss issues.

**Backup (simple, correct):**

- **Stop the container** (or ensure no writes) and **copy the file**; or
- Use SQLite’s online backup: `sqlite3 plant_panel.db ".backup 'backup.db'"`  
  (Plant Pal is low-traffic, so a nightly copy while running is often
  acceptable — but `integrity_check` on the copy is still wise.)

**Restore check:** after copying a backup into place, hit `/healthz` and
`GET /status` — confirm `db.size_bytes` and `schema_version` look sane.

## Troubleshooting

**`pip-compile` picks a version your Docker Python can't run.** The host
venv is Python 3.14 but the image is 3.12. If this ever happens, pass
`--python-version=3.12` to `pip-compile` (or run it inside a 3.12
container). So far all runtime deps support 3.9+ so this hasn't come up.

**`--require-hashes` fails after an OS upgrade.** Usually a platform-
specific wheel was chosen that doesn't exist for your new Python. Fix:
`make upgrade` to regenerate the lock, then rerun the failing install.

**The venv gets into a broken state (e.g. `pip._internal` ImportError).**
Nuke and rebuild:

```bash
rm -rf .venv
make install-dev
```

## Security posture (today)

- Container runs as an unprivileged user (`plantpal`, UID 1000).
- Dependencies are hash-pinned, so PyPI tampering can't silently change the
  image.
- SQLite DB and user data live on a mounted volume at `/app/data`; the image
  is otherwise stateless.
- App binds to `127.0.0.1` by default; the container overrides to `0.0.0.0`
  so Docker's port mapping works.
- `uvicorn --no-server-header` is set in both `run.sh` and the Dockerfile
  `CMD`, so responses don't leak the server name.
- `app/security.py` installs a small middleware stack:
  - `TrustedHostMiddleware` reject unknown Host headers.
  - Every response gets `X-Content-Type-Options: nosniff`, `X-Frame-Options:
    DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and
    `X-Permitted-Cross-Domain-Policies: none`.
  - Content-Security-Policy is opt-in (off by default).
- No secrets are read from the filesystem today. If you add auth later,
  surface secrets through env vars only and document them in `.env.example`.

### Security environment variables

| Env var | Default | Purpose |
|---|---|---|
| `PLANTPAL_ALLOWED_HOSTS` | `*` | Comma-separated list for `TrustedHostMiddleware`. Wildcards like `*.local` and `*.ts.net` work. Leaving this unset logs a one-time warning at startup so you notice in production. Example: `plantpal.local,127.0.0.1,*.ts.net`. |
| `PLANTPAL_ENABLE_CSP` | _unset_ | Set to `1` to emit a `Content-Security-Policy` header. The policy is permissive enough to keep Tailwind Play CDN + Google Fonts + inline scripts working. |
| `PLANTPAL_CSP_REPORT_ONLY` | _unset_ | Set to `1` together with `PLANTPAL_ENABLE_CSP=1` to use `Content-Security-Policy-Report-Only` instead — useful for checking what would break before switching to enforce mode. |

For a typical Pi deployment shared across one or two devices:

```bash
export PLANTPAL_ALLOWED_HOSTS="plantpal.local,*.ts.net,127.0.0.1"
# Leave CSP off until you've confirmed nothing in the UI regresses.
```

### Where to tighten later

- If/when you drop the Tailwind Play CDN in favor of a local build, tighten
  the CSP in `app/security.py` to `default-src 'self'` only and remove the
  CDN / Google Fonts allowances.
- If/when you expose the app publicly, add `HTTPSRedirectMiddleware` in
  `app/security.py` and require a non-wildcard `PLANTPAL_ALLOWED_HOSTS`.
