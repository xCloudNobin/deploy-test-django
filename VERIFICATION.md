# Verification record

Django taskboard — xCloud app-compatibility fixture.

## Candidate commit

- Commit SHA: `pending` (filled by the PR)
- Branch/PR: `feat/compatibility-django` (PR pending reviewer)

## Environment

- Date: 2026-09-20 (UTC)
- Python: 3.11.15
- Django: 5.2.17
- gunicorn: 26.2.0
- Database: SQLite (persistent path) on the same host.
- Category: Django (Python WSGI) framework deployment.
- Build method: `gunicorn -c gunicorn.conf.py config.wsgi:application`
  (production process, not the dev server).

## Local verification (`scripts/verify.sh`)

`scripts/verify.sh` runs each step below and aborts on failure. Full local
run executed on 2026-09-20 with every step passing (exit 0):

1. `scripts/build.sh` — release marker written to `VERSION`.
2. Clean virtualenv + `pip install -r requirements-dev.txt`.
3. `manage.py check` — "System check identified no issues (0 silenced)."
4. `manage.py makemigrations --check --dry-run` — "No changes detected".
5. pytest — **26 passed** (auth/session, CRUD + validation negatives, HTML
   escaping, health/readiness including DB-down 503, worker behavior,
   migration and seed idempotency).
6. `scripts/smoke.sh` — real gunicorn process, **45 passed / 0 failed**:
   - liveness `/health/live` 200 and readiness `/health/ready` 200;
   - login/session cookie flow and wrong-password rejection;
   - HTML project/task create/read/update/delete over HTTP with CSRF;
   - search/filter and XSS-escaping checks;
   - background jobs queued by task writes, drained by
     `runworker --once`, project progress recomputed to 50.0%;
   - negative cases: blank name, invalid status, missing CSRF (403),
     unknown resource (404), anonymous redirect (302);
   - graceful stop → restart on the same SQLite path → persistence survivor
     still served; data counts stable across restart;
   - database-unavailable phase: `/health/live` 200, `/health/ready` 503,
     page route 503.

## Limitations

- Local verification only. Live xCloud category deployment and external
  qualification are **not** claimed; status stays `local-verified` until then.
- SQLite is a reasonable default; production deployments may substitute an
  external PostgreSQL database without changing application code.
- Demo fixtures must not hold sensitive data; `.env.example` uses placeholders
  and no credentials are committed.

## Evidence chain

Command run at the candidate commit: `scripts/verify.sh` (output above
summarized). The smoke summary line was:
`=== Django smoke summary: 45 passed, 0 failed ===`