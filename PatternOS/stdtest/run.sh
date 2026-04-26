#!/usr/bin/env bash
# Linux mirror of stdtest/run.ps1 — staged, low-priority where possible.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
COMPOSE="$ROOT/stdtest/docker-compose.stdtest.yml"
ART="$ROOT/stdtest/.artifacts/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ART"

IONICE=(ionice -c2 -n7)
command -v ionice >/dev/null 2>&1 || IONICE=()

NICE=(nice -n 10)
command -v nice >/dev/null 2>&1 || NICE=()

free_port() {
  local p="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${p}/tcp" >/dev/null 2>&1 || true
  fi
}

wait_http() {
  local url="$1" max="${2:-90}"
  local i=0
  while [[ $i -lt $max ]]; do
    if curl -fsS "$url" >/dev/null 2>&1; then return 0; fi
    sleep 1
    i=$((i + 1))
  done
  echo "Timeout waiting for $url" >&2
  return 1
}

docker_ok() {
  docker info >/dev/null 2>&1
}

USE_DOCKER=false
if docker_ok; then USE_DOCKER=true; fi

cleanup() {
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" >/dev/null 2>&1 || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" >/dev/null 2>&1 || true
  if $USE_DOCKER; then
    docker compose -f "$COMPOSE" down -v >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[stdtest] artifact dir: $ART"

if $USE_DOCKER; then
  echo "[stdtest] starting postgres (docker)…"
  docker compose -f "$COMPOSE" up -d
  export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
  export POSTGRES_PORT="${POSTGRES_PORT:-55432}"
  export POSTGRES_DB="${POSTGRES_DB:-patternos_stdtest}"
  export POSTGRES_USER="${POSTGRES_USER:-patternos}"
  export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-patternos}"
  sleep 3
else
  echo "[stdtest] docker unavailable — using POSTGRES_* from environment / .env"
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT/.env"
    set +a
  fi
  export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
  export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  export POSTGRES_USER="${POSTGRES_USER:-postgres}"
  export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
  export POSTGRES_DB="${POSTGRES_DB:-patternos_stdtest_local}"
fi

for p in 8000 8001 3000 3001; do free_port "$p"; done
sleep 1

export APP_ENV=test
export SCHEDULER_ENABLED=false
export LLM_DISABLED=true
export TELEGRAM_ALERTS_ENABLED=false
export TELEGRAM_MODE=disabled
export PYTHONPATH="$BACKEND"

echo "[stdtest] migrate + seed…"
(
  cd "$BACKEND"
  "${NICE[@]}" "${IONICE[@]}" python3 migrate.py
  "${NICE[@]}" "${IONICE[@]}" python3 scripts/stdtest_seed.py
) >"$ART/migrate_seed.log" 2>&1

echo "[stdtest] backend :8001…"
(
  cd "$BACKEND"
  "${NICE[@]}" "${IONICE[@]}" python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
) >"$ART/backend.log" 2>"$ART/backend.err.log" &
BACK_PID=$!
wait_http "http://127.0.0.1:8001/health" 90

echo "[stdtest] frontend :3001…"
export PORT=3001
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001/api/v1"
(
  cd "$FRONTEND"
  "${NICE[@]}" npm run dev -- --port 3001
) >"$ART/frontend.log" 2>"$ART/frontend.err.log" &
FRONT_PID=$!
wait_http "http://127.0.0.1:3001" 120

echo "[stdtest] pytest…"
(
  cd "$BACKEND"
  "${NICE[@]}" "${IONICE[@]}" python3 -m pytest -q
) | tee "$ART/pytest.log"

echo "[stdtest] playwright…"
export PLAYWRIGHT_BASE_URL="http://127.0.0.1:3001"
export E2E_API_BASE="http://127.0.0.1:8001/api/v1"
(
  cd "$FRONTEND"
  "${NICE[@]}" npm run test:e2e
) | tee "$ART/playwright.log"

echo "[stdtest] OK — artifacts: $ART"
