#!/usr/bin/env bash
# Starts Firecrawl (docker, optional), the backend + agents, and the dashboard.
# Everything listens on 127.0.0.1 only, so nothing is reachable from your network.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ] || [ ! -d dashboard/node_modules ]; then
  echo "Run ./setup.sh first"; exit 1
fi
[ -f .env ] || { echo "Missing .env - copy .env.example and add your ANTHROPIC_API_KEY"; exit 1; }

cleanup() { trap - EXIT INT TERM; kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "▶ Firecrawl stack (docker compose up -d)…"
  docker compose up -d || echo "  ! Firecrawl didn't start - the app still runs without it"
else
  echo "  ! Docker isn't running - skipping Firecrawl (open Docker Desktop to enable it)"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "▶ Backend on http://127.0.0.1:8000"
uvicorn agent.main:app --host 127.0.0.1 --port 8000 &

# Wait for the API before starting the dashboard, so the first page load works
for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done

echo "▶ Dashboard on http://localhost:3000"
(cd dashboard && npm run dev) &

wait
