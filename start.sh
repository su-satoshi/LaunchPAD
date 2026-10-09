#!/usr/bin/env bash
# Starts Firecrawl (docker), the backend + browser agent, and the dashboard.
set -e
cd "$(dirname "$0")"
trap 'kill 0' EXIT

if command -v docker >/dev/null 2>&1; then
  echo "▶ Firecrawl stack (docker compose up -d)…"
  docker compose up -d || echo "  ! Firecrawl didn't start - the app still runs without it"
else
  echo "  ! Docker not installed - skipping Firecrawl"
fi

source .venv/bin/activate
echo "▶ Backend on http://localhost:8000"
uvicorn agent.main:app --port 8000 &

echo "▶ Dashboard on http://localhost:3000"
(cd dashboard && npm run dev) &

wait
