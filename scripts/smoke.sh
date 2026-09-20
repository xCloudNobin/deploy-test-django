#!/usr/bin/env bash
# Reproducible production smoke test for the Django taskboard.
#
# Starts the REAL production process (gunicorn -> config.wsgi), performs
# login/session, HTML CRUD with negative cases, runs the background worker
# against the same SQLite database, restarts gunicorn on the same database
# path to prove persistence, verifies dependency-failure readiness, then
# cleans up. Schema is provisioned with real ORM migrations.
#
# Usage:
#   scripts/smoke.sh            # expects ./.venv (installs deps if missing)
#   VENV=/path scripts/smoke.sh # custom venv, created if missing
#
# Env: DATABASE_NAME defaults to a temp file; override to reuse a db.
# Exit codes: 0 = all checks passed, nonzero = a check failed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"
PY="$VENV/bin/python"
MANAGE="$PY $ROOT/manage.py"

WORK="$(mktemp -d /tmp/django-smoke.XXXXXX)"
PIDFILE="$WORK/server.pid"
JAR="$WORK/cookies.txt"
LOG1="$WORK/server1.log"
LOG2="$WORK/server2.log"
LOG3="$WORK/server-fail.log"
DB="${DATABASE_NAME:-$WORK/tasks.sqlite3}"
UN="$WORK/unreachable.sqlite3"
MISSING_DIR="$WORK/does-not-exist"
SECRET="smoke-only-secret-$(date +%s)"
BASE="http://127.0.0.1"

cleanup() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null || true
    sleep 0.2
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

PASS=0
FAIL=0

ok()   { PASS=$((PASS + 1)); printf 'ok   %s\n' "$*"; }
bad()  { FAIL=$((FAIL + 1)); printf 'FAIL %s\n' "$*"; }

expect_status() { # label url expected method data...
  local label="$1" url="$2" expected="$3" method="$4"
  shift 4
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
    -X "$method" "$@" "$url" || true)
  if [ "$code" = "$expected" ]; then
    ok "$label ($code)"
  else
    bad "$label: expected $expected got $code"
  fi
}

pick_port() {
  "$PY" - <<'EOF'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
EOF
}

db_env() { # db_path -> prints env prefix to use for server/commands
  printf 'DATABASE_NAME=%s DATA_DIR=%s DJANGO_SECRET_KEY=%s ' \
    "$1" "$WORK" "$SECRET"
}

start_server() { # db_path pidfile logfile -> echoes port
  local db_path="$1" pidfile="$2" logfile="$3"
  local port
  port="$(pick_port)"
  local env_prefix port_marker
  env_prefix="$(db_env "$db_path")"
  port_marker="smoke-$port"
  (cd "$ROOT" && eval "export $env_prefix PORT=$port BUILD_MARKER='$port_marker' DJANGO_DEBUG=0 DJANGO_ALLOWED_HOSTS='127.0.0.1,localhost' WEB_CONCURRENCY=1" \
    && "$VENV/bin/gunicorn" -c gunicorn.conf.py config.wsgi:application \
      --daemon -p "$pidfile" --access-logfile "$logfile" --error-logfile "$logfile")
  echo "$port"
}

wait_ready_http() { # port label logfile
  local port="$1" label="$2" logfile="${3:-}"
  local code=000
  for _ in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' \
      "$BASE:$port/health/live" || true)
    [ "$code" = "200" ] && { ok "liveness HTTP 200 ($label)"; return 0; }
    sleep 0.3
  done
  bad "server did not answer /health/live (last code $code, $label)"
  [ -n "$logfile" ] && [ -f "$logfile" ] && tail -10 "$logfile" || true
  return 1
}

stop_server() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 40); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
}

fetch_token() { # url -> echoes csrf token and updates cookie jar
  local token
  token=$(curl -s -b "$JAR" -c "$JAR" "$1" \
    | grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' \
    | sed 's/.*value="//; s/"$//' \
    | head -1 || true)
  printf '%s' "$token"
}

# ---------------------------------------------------------------- bootstrap
if [ ! -x "$VENV/bin/python" ]; then
  echo "creating venv at $VENV"
  python3 -m venv "$VENV"
fi
[ -x "$VENV/bin/python" ] || "$VENV/bin/python" -m ensurepip >/dev/null 2>&1 || true

echo "installing/refreshing dependencies"
"$PY" -m pip install --quiet -r "$ROOT/requirements-dev.txt"

printf '=== Django smoke start: %s ===\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ------------------------------------------------------- schema + accounts
run_manage() { # db_path command...
  local db_path="$1"
  shift
  local env_prefix
  env_prefix="$(db_env "$db_path")"
  (cd "$ROOT" && eval "export $env_prefix" && $MANAGE "$@")
}

rm -f "$DB"
run_manage "$DB" migrate --noinput >/dev/null
ok "migrations applied to fresh database"

run_manage "$DB" seed >/dev/null
c1="$(run_manage "$DB" shell -c \
  'from taskboard.models import Project,Task;print(Project.objects.count(),Task.objects.count())' 2>/dev/null | tail -1)"
run_manage "$DB" seed >/dev/null
c2="$(run_manage "$DB" shell -c \
  'from taskboard.models import Project,Task;print(Project.objects.count(),Task.objects.count())' 2>/dev/null | tail -1)"
if [ "$c1" = "$c2" ]; then ok "seed data is idempotent ($c1)"; else bad "seed changed counts: $c1 -> $c2"; fi

run_manage "$DB" ensureuser --username smokeuser --password s3cret-pass >/dev/null
ok "login user provisioned"

# ------------------------------------------------------- run 1 (create path)
echo "--- phase 1: production start + login + CRUD + worker + negatives (fresh DB)"
PORT1="$(start_server "$DB" "$PIDFILE" "$LOG1")"
wait_ready_http "$PORT1" "phase-1" "$LOG1"

BODY="$(curl -s "$BASE:$PORT1/health/ready")"
case "$BODY" in
  *'"status": "ready"'*) ok "readiness reports ready";;
  *) bad "readiness payload: $BODY";;
esac

MARKER="smoke-$PORT1"
index="$(curl -s "$BASE:$PORT1/accounts/login/")"
case "$index" in
  *"$MARKER"*) ok "build marker rendered on login page";;
  *) bad "build marker missing on login page";;
esac

expect_status "anonymous -> redirected to login" "$BASE:$PORT1/" 302 GET

# login flow
TOKEN="$(fetch_token "$BASE:$PORT1/accounts/login/")"
[ -n "$TOKEN" ] && ok "csrf token acquired from login form" || bad "csrf token missing"
resp=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/accounts/login/" \
  --data-urlencode "username=smokeuser" \
  --data-urlencode "password=s3cret-pass" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
case "$resp" in
  302*) ok "login succeeds with session redirect ($resp)";;
  *) bad "login failed: $resp";;
esac

home="$(curl -s -b "$JAR" "$BASE:$PORT1/")"
case "$home" in
  *"smokeuser"*) ok "session cookie honored (user visible)";;
  *) bad "session not established";;
esac

# wrong-password negative
WRONG="$(fetch_token "$BASE:$PORT1/accounts/login/")"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/accounts/login/" \
  --data-urlencode "username=smokeuser" \
  --data-urlencode "password=wrong" \
  --data-urlencode "csrfmiddlewaretoken=$WRONG")
[ "$resp" = "200" ] && ok "login rejects wrong password (200)" || bad "wrong-password login: $resp"

# create project over HTTP
TOKEN="$(fetch_token "$BASE:$PORT1/projects/new")"
resp=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/projects/new" \
  --data-urlencode "name=Smoke Project" \
  --data-urlencode "description=created over HTTP" \
  --data-urlencode "status=active" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
case "$resp" in
  302*) ok "HTML create project ($resp)";;
  *) bad "HTML create project: $resp";;
esac
PROJECT_URL="${resp#302 }"
PROJECT_ID="$(basename "$PROJECT_URL")"

# create tasks (one done, one todo) to feed the background worker
TOKEN="$(fetch_token "$BASE:$PORT1/tasks/new")"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/tasks/new" \
  --data-urlencode "project=$PROJECT_ID" \
  --data-urlencode "title=Smoke Task done" \
  --data-urlencode "description=over http" \
  --data-urlencode "status=done" \
  --data-urlencode "priority=high" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "HTML create task (done)" || bad "HTML create task: $resp"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/tasks/new" \
  --data-urlencode "project=$PROJECT_ID" \
  --data-urlencode "title=Smoke Task todo" \
  --data-urlencode "description=" \
  --data-urlencode "status=todo" \
  --data-urlencode "priority=low" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "HTML create task (todo)" || bad "HTML create task: $resp"

# read back on project detail
detail="$(curl -s -b "$JAR" "$PROJECT_URL")"
hits=0
case "$detail" in *"Smoke Task done"*) hits=$((hits + 1));; esac
case "$detail" in *"Smoke Task todo"*) hits=$((hits + 1));; esac
if [ "$hits" = "2" ]; then ok "read: both tasks listed on project page"; else bad "tasks not listed on project page"; fi

# search/filter
search_hit="$(curl -s -b "$JAR" "$BASE:$PORT1/tasks/?q=done")"
case "$search_hit" in
  *"Smoke Task done"*) ok "search finds matching task";;
  *) bad "search missing task";;
esac
case "$search_hit" in
  *"Smoke Task todo"*) bad "search leaked non-matching task";;
  *) ok "search excludes non-matching task";;
esac

# background job: queued after task writes, drained by the worker command
Q="$(run_manage "$DB" shell -c \
  'from jobs.models import Job;print(Job.objects.filter(status="queued").count())' 2>/dev/null | tail -1)"
if [ "${Q:-0}" -ge 2 ]; then ok "background jobs queued by task writes (queued=$Q)"; else bad "jobs not queued: queued=$Q"; fi

run_manage "$DB" runworker --once >/dev/null
RES="$(run_manage "$DB" shell -c \
  "from jobs.models import Job;from taskboard.models import Project;print(Project.objects.get(pk=$PROJECT_ID).progress, Job.objects.filter(status='succeeded').count())" 2>/dev/null | tail -1)"
case "$RES" in
  50.0*) ok "worker recomputed project progress 50.0% ($RES)";;
  *) bad "worker progress wrong: $RES";;
esac

# update task
TASK_ID=$(echo "$detail" | grep -o "/tasks/[0-9]\+/edit" \
  | head -1 | sed 's#/tasks/##; s#/edit##' || true)
[ -n "$TASK_ID" ] && ok "discovered task id $TASK_ID" || bad "task id not found"
TOKEN="$(fetch_token "$BASE:$PORT1/tasks/$TASK_ID/edit")"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/tasks/$TASK_ID/edit" \
  --data-urlencode "project=$PROJECT_ID" \
  --data-urlencode "title=Smoke Task (updated)" \
  --data-urlencode "description=" \
  --data-urlencode "status=in_progress" \
  --data-urlencode "priority=medium" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "HTML update task (302)" || bad "HTML update task: $resp"
updated="$(curl -s -b "$JAR" "$PROJECT_URL")"
case "$updated" in
  *"Smoke Task (updated)"*) ok "read-back confirms update";;
  *) bad "update not reflected";;
esac

# update project
TOKEN="$(fetch_token "$BASE:$PORT1/projects/$PROJECT_ID/edit")"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/projects/$PROJECT_ID/edit" \
  --data-urlencode "name=Smoke Project (renamed)" \
  --data-urlencode "description=edited" \
  --data-urlencode "status=active" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "HTML update project (302)" || bad "HTML update project: $resp"

# delete a throwaway task
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/tasks/new" \
  --data-urlencode "project=$PROJECT_ID" \
  --data-urlencode "title=throwaway" \
  --data-urlencode "status=todo" \
  --data-urlencode "priority=low" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "HTML create throwaway task (302)" || bad "HTML create throwaway: $resp"
THROW_ID="$(run_manage "$DB" shell -c \
  "from taskboard.models import Task;print(Task.objects.get(title='throwaway').pk)" 2>/dev/null | tail -1)"
[ -n "$THROW_ID" ] && ok "throwaway task id $THROW_ID" || bad "throwaway task id missing"
TOKEN="$(fetch_token "$BASE:$PORT1/tasks/$THROW_ID/delete")"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/tasks/$THROW_ID/delete" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "HTML delete task (302)" || bad "HTML delete task: $resp"
gone="$(curl -s -b "$JAR" "$PROJECT_URL")"
case "$gone" in
  *"throwaway"*) bad "deleted task still visible";;
  *) ok "deleted task no longer visible";;
esac

# XSS escaping
TOKEN="$(fetch_token "$BASE:$PORT1/tasks/new")"
curl -s -o /dev/null -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/tasks/new" \
  --data-urlencode "project=$PROJECT_ID" \
  --data-urlencode "title=<script>alert(1)</script>" \
  --data-urlencode "status=todo" \
  --data-urlencode "priority=medium" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN"
esc="$(curl -s -b "$JAR" "$BASE:$PORT1/tasks/")"
case "$esc" in
  *"<script>alert(1)</script>"*) bad "XSS not escaped";;
  *"&lt;script&gt;"*) ok "output escaped (no XSS)";;
  *) ok "output escaped (no raw script tag)";;
esac

# ---- negatives
expect_status "blank project name -> 200 (error)" "$BASE:$PORT1/projects/new" 200 POST \
  --data-urlencode "name=   " --data-urlencode "status=active" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN"
expect_status "invalid task status -> 200 (error)" "$BASE:$PORT1/tasks/new" 200 POST \
  --data-urlencode "project=$PROJECT_ID" --data-urlencode "title=x" \
  --data-urlencode "status=warp" --data-urlencode "csrfmiddlewaretoken=$TOKEN"
expect_status "missing csrf -> 403" "$BASE:$PORT1/projects/new" 403 POST \
  --data-urlencode "name=X" --data-urlencode "status=active"
expect_status "unknown project -> 404" "$BASE:$PORT1/projects/999999" 404 GET
expect_status "unknown task edit -> 404" "$BASE:$PORT1/tasks/999999/edit" 404 GET
TOKEN="$(fetch_token "$BASE:$PORT1/tasks/new")"
errbody="$(curl -s -b "$JAR" -c "$JAR" -X POST \
  --data-urlencode "project=$PROJECT_ID" \
  --data-urlencode "title=   " \
  --data-urlencode "status=todo" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN" \
  "$BASE:$PORT1/tasks/new")"
case "$errbody" in
  *"required"*) ok "meaningful validation error rendered";;
  *) bad "validation error body unexpected";;
esac

# logout then verify anonymous protection again
TOKEN="$(fetch_token "$BASE:$PORT1/accounts/login/")"
resp=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/accounts/logout/" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
[ "$resp" = "302" ] && ok "logout succeeds" || bad "logout failed: $resp"
expect_status "post-logout anonymous blocked" "$BASE:$PORT1/" 302 GET

# ------------------------------------------------------ persistence survivor
TOKEN="$(fetch_token "$BASE:$PORT1/accounts/login/")"
curl -s -o /dev/null -b "$JAR" -c "$JAR" -X POST "$BASE:$PORT1/accounts/login/" \
  --data-urlencode "username=smokeuser" --data-urlencode "password=s3cret-pass" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN"
TOKEN="$(fetch_token "$BASE:$PORT1/projects/new")"
resp=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -b "$JAR" -c "$JAR" \
  -X POST "$BASE:$PORT1/projects/new" \
  --data-urlencode "name=PERSIST-$$-survivor" \
  --data-urlencode "description=must survive restart" \
  --data-urlencode "status=active" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN")
SURVIVOR_URL="${resp#302 }"
SURVIVOR_PATH="${SURVIVOR_URL#"$BASE:$PORT1"}"
if [ -n "$SURVIVOR_PATH" ]; then ok "persistence survivor created ($SURVIVOR_URL)"; else bad "survivor not created"; fi

if [ -f "$DB" ]; then
  bytes=$(wc -c < "$DB")
  [ "$bytes" -gt 0 ] && ok "sqlite data stored on disk ($bytes bytes)" || bad "database file empty"
else
  bad "database file missing at configured path"
fi

echo "--- phase 2: graceful stop, restart on same sqlite path"
counts_before="$(run_manage "$DB" shell -c \
  'from taskboard.models import Project,Task;print(Project.objects.count(),Task.objects.count())' 2>/dev/null | tail -1)"
stop_server
sleep 0.3

echo "--- phase 3: restart persistence check"
PORT2="$(start_server "$DB" "$PIDFILE" "$LOG2")"
wait_ready_http "$PORT2" "phase-3" "$LOG2"
found="$(curl -s -b "$JAR" "$BASE:$PORT2$SURVIVOR_PATH")"
case "$found" in
  *"PERSIST-$$-survivor"*) ok "persistence: survivor project survived restart";;
  *) bad "persistence FAILED: survivor missing after restart";;
esac

seed_after="$(run_manage "$DB" shell -c \
  'from taskboard.models import Project,Task;print(Project.objects.count(),Task.objects.count())' 2>/dev/null | tail -1)"
case "$seed_after" in
  "$counts_before") ok "data counts stable across restart ($counts_before)";;
  *) bad "counts changed across restart: $counts_before -> $seed_after";;
esac
stop_server

echo "--- phase 4: dependency failure (database unavailable)"
PORT3="$(start_server "$MISSING_DIR/unreachable.sqlite3" "$PIDFILE" "$LOG3")"
wait_ready_http "$PORT3" "phase-4" "$LOG3"
expect_status "liveness /health/live still 200" "$BASE:$PORT3/health/live" 200 GET
expect_status "readiness /health/ready -> 503" "$BASE:$PORT3/health/ready" 503 GET
expect_status "page route / -> 503" "$BASE:$PORT3/" 503 GET
stop_server

echo
printf '=== Django smoke summary: %s passed, %s failed ===\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]