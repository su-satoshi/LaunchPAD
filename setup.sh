#!/usr/bin/env bash
# LaunchPAD / Orion AI - one-time setup (macOS or Linux)
set -e
cd "$(dirname "$0")"
B='\033[1m'; G='\033[0;32m'; Y='\033[1;33m'; N='\033[0m'

echo -e "${B}[1/5] Python backend${N}"
PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ needed (Stagehand)"'
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r agent/requirements.txt
# Playwright's Chromium is only the fallback; Stagehand uses your installed Google Chrome
python -m playwright install chromium >/dev/null 2>&1 || echo -e "${Y}  (skipped Playwright Chromium download)${N}"
echo -e "${G}  ✓ backend ready${N}"

echo -e "${B}[2/5] Dashboard${N}"
(cd dashboard && npm install --silent)
echo -e "${G}  ✓ dashboard ready${N}"

echo -e "${B}[3/5] .env${N}"
if [ ! -f .env ]; then cp .env.example .env; echo -e "${Y}  Created .env - add your ANTHROPIC_API_KEY${N}"; else echo -e "${G}  ✓ .env exists${N}"; fi

echo -e "${B}[4/5] Google Chrome (for the Stagehand browser agent)${N}"
if [ -d "/Applications/Google Chrome.app" ] || command -v google-chrome >/dev/null 2>&1; then
  echo -e "${G}  ✓ Chrome found${N}"
else
  echo -e "${Y}  Chrome not found - install it, or the agent falls back to read-only Playwright${N}"
fi

echo -e "${B}[5/5] Docker (for self-hosted Firecrawl)${N}"
if command -v docker >/dev/null 2>&1; then
  echo -e "${G}  ✓ Docker found. First 'docker compose up' builds Firecrawl from source (~10 min).${N}"
else
  echo -e "${Y}  Docker not found - install Docker Desktop to enable the Firecrawl source${N}"
fi

echo ""
echo -e "${B}Done.${N} Start everything with: ${B}./start.sh${N}  then open http://localhost:3000"
