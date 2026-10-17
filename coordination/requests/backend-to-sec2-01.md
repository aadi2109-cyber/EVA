# Request backend-to-sec2-01
Status: OPEN
From: BE · To: SEC-2 · Date: 2026-10-16

## Need
Please add `guard/Dockerfile` for the standalone service in `guard/service/main.py`.

## Why / what breaks without it
`docker compose -f env/docker-compose.yml up --build` now starts both the API and its HTTP guard. Compose builds the service from `guard/`; without a Dockerfile, the required default Compose command fails before either service can start.

## Proposed change (exact schema/file diff if a contract change)
Add a Python 3.12 image with the guard dependencies and `contracts/` available on `PYTHONPATH`, copy the `guard/` and `contracts/` sources, expose port 8100, and run `uvicorn service.main:app --host 0.0.0.0 --port 8100`. Keep the service on the existing `GUARD_SERVICE_TOKEN` and `GUARD_DATABASE_URL` environment settings. Do not include agent/backend sources.

## Answer (recipient fills in)
