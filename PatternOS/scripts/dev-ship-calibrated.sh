#!/usr/bin/env bash
# Run heavy checks one stage at a time with nice/ionice (leaves headroom for other workloads).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IONICE=(ionice -c2 -n7)
command -v ionice >/dev/null 2>&1 || IONICE=()
NICE=(nice -n 10)
command -v nice >/dev/null 2>&1 || NICE=()

echo "[dev-ship] backend pytest"
(
  cd "$ROOT/backend"
  export PYTHONPATH=.
  "${NICE[@]}" "${IONICE[@]}" python3 -m pytest -q
)

echo "[dev-ship] frontend build"
(
  cd "$ROOT/frontend"
  "${NICE[@]}" npm run build
)

if [[ -n "${PLAYWRIGHT_BASE_URL:-}" && -n "${E2E_API_BASE:-}" ]]; then
  echo "[dev-ship] playwright (PLAYWRIGHT_BASE_URL set)"
  (
    cd "$ROOT/frontend"
    "${NICE[@]}" npm run test:e2e
  )
else
  echo "[dev-ship] skip playwright (set PLAYWRIGHT_BASE_URL + E2E_API_BASE to run)"
fi

echo "[dev-ship] done"
