# EVA Guard HTTP service. Build context MUST be the repo root (contracts/ lives outside guard/):
#   docker build -f guard/Dockerfile -t eva-guard .
# compose: guard: { build: { context: .., dockerfile: guard/Dockerfile } }
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/guard:/app \
    APP_ENV=prod

WORKDIR /app/guard

COPY guard/pyproject.toml ./pyproject.toml
RUN python - <<'PY' > /tmp/requirements.txt
import tomllib
deps = tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]
# SEC-1's ONNX Tier-2 scorer runtime
print("\n".join(deps + ["onnxruntime>=1.17.0", "numpy>=1.26"]))
PY
RUN pip install -r /tmp/requirements.txt

# Guard source + shared contracts only (no agent/backend sources).
COPY contracts /app/contracts
COPY guard /app/guard

# Unprivileged user; /data holds guard.db (policies, approvals, audit chain, config) and must be a volume.
RUN useradd --system --uid 10002 --home /data eva-guard && mkdir -p /data && chown -R eva-guard /data
USER eva-guard

EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/v1/health', timeout=2)"
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8100"]
