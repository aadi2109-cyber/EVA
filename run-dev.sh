#!/usr/bin/env bash
# Start EVA backend (uvicorn :8000) and frontend (vite :5173) together.
# Ctrl+C stops both. Override with BACKEND_PORT / FRONTEND_PORT.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

export PYTHONPATH="$ROOT/agent/backend:$ROOT:$ROOT/contracts:$ROOT/guard${PYTHONPATH:+:$PYTHONPATH}"
export VITE_API_BASE="${VITE_API_BASE:-http://localhost:$BACKEND_PORT}"

# Backend: migrate, then serve
cd "$ROOT/agent/backend"
alembic upgrade head
uvicorn app.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!

# Frontend: install deps on first run
cd "$ROOT/agent/frontend"
[ -d node_modules ] || npm install
npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

cleanup() {
  trap - INT TERM EXIT
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Backend:  http://localhost:$BACKEND_PORT  (health: /api/health)"
echo "Frontend: http://localhost:$FRONTEND_PORT"

# Exit as soon as either process dies
wait -n "$BACKEND_PID" "$FRONTEND_PID"
