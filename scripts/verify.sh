#!/usr/bin/env bash
# Full verification for the Django taskboard fixture:
#
#   1. build.sh -> non-sensitive release marker (VERSION)
#   2. fresh virtualenv -> clean install of requirements-dev.txt
#   3. manage.py check + makemigrations --check (schema in sync)
#   4. pytest (unit/smoke/error/persistence logic tests)
#   5. scripts/smoke.sh (real gunicorn production process, HTTP CRUD,
#      background worker, restart persistence, dependency-failure readiness)
#
# Usage:
#   scripts/verify.sh
#   KEEP_VENV=1 scripts/verify.sh   # keep the build venv for inspection
#
# Exit codes: 0 = all checks passed, nonzero = a check failed. The first
# failing step aborts with its own nonzero code.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORK="$(mktemp -d /tmp/django-verify.XXXXXX)"
VENV="$WORK/venv"

cleanup() {
  if [ "${KEEP_VENV:-0}" != "1" ]; then
    rm -rf "$WORK"
  else
    echo "kept build venv at $VENV"
  fi
}
trap cleanup EXIT

step() { printf '\n=== %s ===\n' "$*"; }

step "build release marker (VERSION)"
"$ROOT/scripts/build.sh"

step "clean install in fresh venv"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements-dev.txt"

step "Django system check"
(cd "$ROOT" && "$VENV/bin/python" manage.py check)

step "makemigrations --check (no pending schema changes)"
(cd "$ROOT" && "$VENV/bin/python" manage.py makemigrations --check --dry-run)

step "pytest unit/integration suite"
(cd "$ROOT" && "$VENV/bin/python" -m pytest -v)

step "production smoke: gunicorn + CRUD + worker + persistence + readiness"
VENV="$VENV" "$ROOT/scripts/smoke.sh"

step "verification complete (all steps passed)"
printf '%s\n' "python: $("$VENV/bin/python" --version)"
printf '%s\n' "django: $("$VENV/bin/python" -c 'import django;print(django.get_version())')"
printf '%s\n' "gunicorn: $("$VENV/bin/python" -c 'import gunicorn;print(gunicorn.__version__)')"