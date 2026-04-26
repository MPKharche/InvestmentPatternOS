#!/usr/bin/env bash
# Production PatternOS UI: one optimized build, then next start (lower CPU/RAM than `npm run dev`).
# Usage: from repo root —  ./scripts/run-frontend-prod.sh
# Port: set PORT (default 3000). API URL: set NEXT_PUBLIC_API_BASE_URL before running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
export PORT="${PORT:-3000}"
echo "[frontend-prod] PORT=$PORT  (set NEXT_PUBLIC_API_BASE_URL if the API is not same-origin)"
npm run build
exec npm run start
