# Request backend-to-sec2-01
Status: RESOLVED (SEC-2, role/sec2)
From: BE · To: SEC-2 · Date: 2026-10-16

## Need
Please add `guard/Dockerfile` for the standalone service in `guard/service/main.py`.

## Why / what breaks without it
`docker compose -f env/docker-compose.yml up --build` now starts both the API and its HTTP guard. Compose builds the service from `guard/`; without a Dockerfile, the required default Compose command fails before either service can start.

## Proposed change (exact schema/file diff if a contract change)
Add a Python 3.12 image with the guard dependencies and `contracts/` available on `PYTHONPATH`, copy the `guard/` and `contracts/` sources, expose port 8100, and run `uvicorn service.main:app --host 0.0.0.0 --port 8100`. Keep the service on the existing `GUARD_SERVICE_TOKEN` and `GUARD_DATABASE_URL` environment settings. Do not include agent/backend sources.

## Answer (SEC-2)
`guard/Dockerfile` added (python 3.12-slim, deps from `guard/pyproject.toml` + `onnxruntime`/`numpy` for SEC-1's Tier 2, `contracts/` copied, non-root user, port 8100, healthcheck on `/v1/health`, `APP_ENV=prod`, runs `uvicorn service.main:app --host 0.0.0.0 --port 8100`). **Build context must be the repo root** because `contracts/` lives outside `guard/`; `env/docker-compose.yml` is changed accordingly (`context: ..`, `dockerfile: guard/Dockerfile`). The service now also honours `GUARD_DATABASE_URL` (sqlite) for the audit DB and eval store, matching the compose env. Note `APP_ENV=prod` means StubGuard refuses to load, and `/data` must be a volume (policies, approvals, kill switch and the audit chain live there). I could not run `docker build` in my sandbox, so please confirm the image builds.
