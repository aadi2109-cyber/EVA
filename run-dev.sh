#!/usr/bin/env bash
# Start the EVA backend (uvicorn) and frontend (vite) together.
#   ./run-dev.sh            # backend :8000, frontend :5173
#   BACKEND_PORT=9000 FRONTEND_PORT=3000 ./run-dev.sh
# Ctrl+C stops both; if either dies the other is stopped too.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_DIR="$ROOT/agent/backend"
FRONTEND_DIR="$ROOT/agent/frontend"

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' not found on PATH"; }

need npm
if [ -f "$BACKEND_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$BACKEND_DIR/.venv/bin/activate"
elif [ -f "$ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$ROOT/.venv/bin/activate"
fi
PY="$(command -v python3 || command -v python)" || die "python not found"
"$PY" -c "import uvicorn, alembic" 2>/dev/null \
  || die "backend deps missing: cd agent/backend && pip install -e '.[dev]'  (or uv sync)"

export PYTHONPATH="$BACKEND_DIR:$ROOT:$ROOT/contracts:$ROOT/guard${PYTHONPATH:+:$PYTHONPATH}"
export VITE_API_BASE="${VITE_API_BASE:-http://localhost:$BACKEND_PORT}"

# Job control puts each background job in its own process group, so cleanup can
# take down npm -> vite and uvicorn --reload workers, not just the direct child.
set -m
PIDS=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# main rejects a short/placeholder JWT_SECRET (env/.env.example ships one): make sure
# the git-ignored env/.env holds a real one.
"$PY" "$ROOT/scripts/ensure_jwt_secret.py" "$ROOT/env/.env" || die "JWT_SECRET problem (see above)"

echo ">> migrating database"
(cd "$BACKEND_DIR" && "$PY" -m alembic upgrade head)

echo ">> starting backend on :$BACKEND_PORT"
(cd "$BACKEND_DIR" && exec "$PY" -m uvicorn app.main:app --reload --port "$BACKEND_PORT") &
PIDS+=($!)

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo ">> installing frontend dependencies"
  (cd "$FRONTEND_DIR" && npm install)
fi

echo ">> starting frontend on :$FRONTEND_PORT"
(cd "$FRONTEND_DIR" && exec npm run dev -- --port "$FRONTEND_PORT" --strictPort) &
PIDS+=($!)

echo
echo "Backend:  http://localhost:$BACKEND_PORT  (health: /api/health)"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Ctrl+C to stop."

wait -n "${PIDS[@]}" || true
