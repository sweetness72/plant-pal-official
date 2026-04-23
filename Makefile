# Plant Pal — common dev + maintenance tasks.
#
# Every target assumes a virtualenv at .venv/. Create it with `make venv`
# (idempotent). Everything else uses the venv's Python explicitly, so you
# don't need to remember to `source .venv/bin/activate` first.
#
# Dependency model:
#   requirements.in          -> human-edited runtime deps (loose constraints)
#   requirements-dev.in      -> human-edited dev deps
#   requirements.lock        -> generated, hash-pinned runtime graph
#   requirements-dev.lock    -> generated, hash-pinned dev graph
#   requirements-tools.txt   -> pip-tools + pip-audit (bootstrap only)
#
# Common flow:
#   make install-dev     # one-time setup (installs tools + dev lock)
#   make dev             # run with autoreload
#   make check           # lint + format check + tests (pre-push)
#   make audit           # scan the lock for known CVEs
#
# Monthly:
#   make upgrade         # rebuild locks with latest compatible versions
#   make audit           # verify no new CVEs
#   make check           # verify nothing broke
#   git diff requirements*.lock

.PHONY: venv install install-dev sync lock upgrade audit run dev test \
        lint format check ci monthly clean docker docker-pin-base help

VENV       := .venv
PY         := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
PIP_COMPILE:= $(VENV)/bin/pip-compile
PIP_SYNC   := $(VENV)/bin/pip-sync
PIP_AUDIT  := $(VENV)/bin/pip-audit
RUFF       := $(VENV)/bin/ruff

help:
	@echo "Plant Pal — make targets"
	@echo ""
	@echo "Setup:"
	@echo "  install      install runtime lock + tools into .venv"
	@echo "  install-dev  install dev lock + tools into .venv"
	@echo "  sync         prune .venv to match dev lock exactly"
	@echo ""
	@echo "Run:"
	@echo "  dev          run the server with autoreload"
	@echo "  run          run the server (no reload)"
	@echo ""
	@echo "Quality:"
	@echo "  test         run the pytest suite"
	@echo "  lint         ruff check (no writes)"
	@echo "  format       ruff format + ruff check --fix (writes)"
	@echo "  check        lint + format-check + tests; no writes (pre-push)"
	@echo "  ci           check + audit (pre-push gate; mirrors future CI)"
	@echo ""
	@echo "Maintenance:"
	@echo "  lock             regenerate lock files from .in inputs"
	@echo "  upgrade          regenerate locks with latest compatible versions"
	@echo "  audit            scan the lock for known vulnerabilities (pip-audit)"
	@echo "  monthly          full monthly routine (upgrade+sync+audit+check)"
	@echo "  docker-pin-base  print current digest of the Python base image"
	@echo ""
	@echo "Other:"
	@echo "  clean        remove caches (.pytest_cache / .ruff_cache / __pycache__)"
	@echo "  docker       build the local Docker image"

# ----- venv + install --------------------------------------------------------

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PY) -m pip install --upgrade --quiet pip

# Tools come from an un-pinned bootstrap file; everything else flows from the
# lock. --require-hashes is what actually makes the install reproducible.
install: venv
	$(PIP) install --quiet -r requirements-tools.txt
	$(PIP) install --quiet --require-hashes -r requirements.lock

install-dev: venv
	$(PIP) install --quiet -r requirements-tools.txt
	$(PIP) install --quiet --require-hashes -r requirements.lock
	$(PIP) install --quiet --require-hashes -r requirements-dev.lock

# pip-sync prunes anything in .venv that isn't in the lock. Useful after
# removing a dep: `pip install` alone would leave the old package behind.
sync: venv
	$(PIP_SYNC) --quiet requirements.lock requirements-dev.lock

# ----- run -------------------------------------------------------------------

run:
	./run.sh

dev:
	./run.sh reload

# ----- quality ---------------------------------------------------------------

test:
	$(PY) -m pytest

lint:
	$(RUFF) check .

format:
	$(RUFF) format .
	$(RUFF) check --fix .

check:
	$(RUFF) check .
	$(RUFF) format --check .
	$(PY) -m pytest

# `ci` is the one-stop gate we'd run in GitHub Actions if/when we add it.
# Today it lives locally — run before every push / merge to main.
ci: check audit

# ----- maintenance -----------------------------------------------------------

# Recompile the locks from the .in files. Use after editing a .in by hand,
# e.g. to add or remove a direct dependency. Does NOT upgrade pinned
# versions that are already satisfied — use `make upgrade` for that.
lock:
	$(PIP_COMPILE) --generate-hashes --strip-extras --quiet \
		--output-file=requirements.lock requirements.in
	$(PIP_COMPILE) --generate-hashes --strip-extras --quiet \
		--output-file=requirements-dev.lock requirements-dev.in

# Recompile both locks, asking pip-tools to upgrade every package to its
# newest compatible version. This is the once-a-month patching command.
# After running, always `make audit` and `make check` before committing.
upgrade:
	$(PIP_COMPILE) --upgrade --generate-hashes --strip-extras --quiet \
		--output-file=requirements.lock requirements.in
	$(PIP_COMPILE) --upgrade --generate-hashes --strip-extras --quiet \
		--output-file=requirements-dev.lock requirements-dev.in
	@echo ""
	@echo "Locks regenerated. Next:"
	@echo "  make sync && make audit && make check"
	@echo "  git diff requirements*.lock"

# pip-audit hits the PyPI advisory database. `--strict` makes it fail on any
# match (suitable for CI / make check later). We audit the runtime lock only
# by default; dev tools aren't in the shipped image.
audit:
	$(PIP_AUDIT) --strict --requirement requirements.lock

# `monthly` is the first-of-the-month routine documented in MAINTENANCE.md.
# Run this, eyeball `git diff requirements*.lock`, then rebuild Docker.
# We intentionally do NOT run `make docker` here — the diff step is a
# human checkpoint, not an automated one.
monthly: upgrade sync audit check
	@echo ""
	@echo "Monthly routine complete. Next:"
	@echo "  git diff requirements*.lock      # eyeball the diff"
	@echo "  make docker && docker run ...    # rebuild + smoke-test image"

# ----- misc ------------------------------------------------------------------

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

docker:
	docker build -t plant-pal:local .

# Prints the current digest of our Python base image. Paste it into the
# Dockerfile (e.g. `FROM python:3.12-slim-bookworm@sha256:...`) for strict
# reproducibility. Left as an opt-in manual step so routine monthly rebuilds
# continue to pick up OS patches from the moving tag.
docker-pin-base:
	@echo "Current digest of python:3.12-slim-bookworm:"
	@docker buildx imagetools inspect python:3.12-slim-bookworm \
		--format '{{json .Manifest}}' 2>/dev/null \
		| python3 -c "import sys, json; m=json.load(sys.stdin); print(m.get('digest','(not found)'))" \
		|| echo "(docker buildx imagetools not available; fall back to 'docker pull python:3.12-slim-bookworm' and read the digest from the pull output)"
