# EVA agent backend. Build context MUST be the repo root:
#   docker build -f agent/backend/Dockerfile -t eva-api .
# (compose does this: context ".." from env/docker-compose.yml)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/agent/backend:/app/guard:/app/contracts

WORKDIR /app/agent/backend

# Dependencies first (cache-friendly). guard is imported in-process (GUARD_TRANSPORT=inprocess),
# so its runtime deps are installed here too.
COPY agent/backend/pyproject.toml ./pyproject.toml
RUN python - <<'PY' > /tmp/requirements.txt
import tomllib
deps = tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]
print("\n".join(deps + ["pyyaml>=6.0.1", "prometheus-client>=0.20.0"]))
PY
RUN pip install -r /tmp/requirements.txt

# Source: backend, shared contracts, in-process guard facade, mock environment fixtures.
COPY contracts /app/contracts
COPY guard /app/guard
COPY env /app/env
COPY agent/backend /app/agent/backend

# Unprivileged runtime user; /data holds the SQLite DB and per-user workspaces (a volume in compose).
RUN useradd --system --uid 10001 --home /data eva && mkdir -p /data/workspace && chown -R eva /data /app/env/mock
USER eva
ENV DATABASE_URL=sqlite+aiosqlite:////data/agent.db \
    WORKSPACE_ROOT=/data/workspace \
    MOCK_STATE_FILE=/data/mock_state.json

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status < 500 else 1)"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
