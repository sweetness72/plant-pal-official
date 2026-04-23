# Testing Plant Pal

Focus is **correctness and regression safety** for the plant-care **engine** and **SQLite-backed behavior**, not line coverage. Most UI is server-rendered Jinja; only **infrastructure** routes are tested with HTTP (security / health). That split is intentional to keep the suite small and fast.

## How to run

```bash
# one-time: dev venv with hash-pinned locks (see Makefile)
make install-dev

# full suite (same as `make test`)
.venv/bin/python -m pytest tests/

# one file
.venv/bin/python -m pytest tests/test_drying_model.py -v

# one test
.venv/bin/python -m pytest tests/test_scenarios.py::TestCactusLifecycle -v
```

`make check` runs Ruff + pytest together (pre-push).

## Strategy by layer

| Layer | What | Where |
|-------|------|--------|
| **Unit** | Pure functions: modifiers, `effective_drying_days`, `predicted_dry_date`, action generation, `recommend_for_plant` shape | `test_drying_model.py` |
| **DB integration** | Real SQLite in `tmp_path`: `log_watered`, observations, stats, `plant_event`, add/remove | `test_coefficient_learning.py`, `test_recommendation.py`, `test_recommendation_v2.py`, `test_scenarios.py`, `test_known_issues.py` |
| **Service glue** | `core.service` calls match engine + DB (today’s list, per-plant recommendation) | `test_service.py` |
| **HTTP / security** | Middleware, `/healthz`, `/status` (reloads `app` with env) | `test_security.py` |

**Not in scope (deliberate):** full browser or template snapshot tests, coverage gates, property-based tests. If route handlers grow real logic, add a small `tests/test_routes/` set later.

## File tour

| File | Purpose |
|------|---------|
| `tests/conftest.py` | `make_plant` / `make_template` factories; shared **`tmp_db`** (isolated DB + migrations) |
| `test_drying_model.py` | Engine contracts; parametrized edge cases |
| `test_coefficient_learning.py` | Coefficient learning via `log_watered` |
| `test_recommendation.py` | Phase-1 recommendation + observation persistence |
| `test_recommendation_v2.py` | EWMA stats, learned interval, CoV confidence, `plant_event` |
| `test_scenarios.py` | Multi-day “stories” (cactus, fern, streaks) |
| `test_known_issues.py` | Fixed bugs (B1/B2), validation pins, clamping; some tests document **current** edge behavior |
| `test_service.py` | `get_todays_recommendations` / `get_plant_recommendation` + minimal add/remove |
| `test_security.py` | Health, status, response headers, CSP, trusted host |

## Shared fixture: `tmp_db`

All DB integration tests use the same **`tmp_db`** from `conftest.py`. It monkeypatches `core.db.DB_PATH` and `core.db.DATA_DIR` under `tmp_path`, then runs `init_db()` (migrations). Nothing touches `data/plant_panel.db` in tests.

## Categories (intent)

1. **Contract** — Public engine behavior that should stay stable (`test_drying_model.py`).
2. **Integration** — Persistence and learning through SQLite (`test_coefficient_learning.py`, `test_recommendation*.py`, `test_scenarios.py`).
3. **Pinning** — Asserts *current* magic numbers or edge behavior so a diff forces a conscious update to `ASSUMPTIONS.md` (scenarios, parts of `test_known_issues.py`).
4. **Regressions** — Former bugs (e.g. first-watering streak, future `last_watered_date`) live as **normal** tests in `test_known_issues.py` now that behavior is fixed.

## What is intentionally light or absent

- **Jinja / CSS** — Not tested; refactors there are manual.
- **Migrations** — Exercised via `init_db()` everywhere; no separate migration step tests until migration logic grows.
- **`/`, `/plants`, add-plant forms** — No `TestClient` except security/ops routes.

## Adding a test

1. Pure math / engine? → `test_drying_model.py` with `make_plant` / `make_template`.
2. Needs DB writes? → `tmp_db` + `core` DB API.
3. New cross-cutting glue? → `test_service.py`.
4. New middleware or env-driven behavior? → `test_security.py` (note the reload pattern).

## Historical note

Older docs listed **xfail**-based bugs (B1/B2). Those are **fixed** and covered by regular tests in `test_known_issues.py` (`TestStreakBugFixed`, `TestFutureWateredDateFixed`). The workflow in that file’s module doc (xfail for *new* confirmed bugs) still applies if you add one.
