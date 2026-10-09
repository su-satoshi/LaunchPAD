#!/bin/bash
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BOLD}${BLUE}╔════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║     AI Job Pilot — Setup       ║${NC}"
echo -e "${BOLD}${BLUE}╚════════════════════════════════╝${NC}"
echo ""

# ── 1. Python virtualenv ─────────────────────────────────────────────────
echo -e "${BOLD}[1/5] Setting up Python backend...${NC}"
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 RUSTFLAGS="-Z build-std-core"
pip install -q -r requirements.txt || true
cd ..
echo -e "${GREEN}✓ Python dependencies installed${NC}"

# ── 2. Node / Next.js ────────────────────────────────────────────────────
echo -e "${BOLD}[2/5] Installing dashboard dependencies...${NC}"
cd dashboard
if command -v pnpm &>/dev/null; then
  pnpm install --silent
elif command -v yarn &>/dev/null; then
  yarn install --silent
else
  npm install --silent
fi
cd ..
echo -e "${GREEN}✓ Dashboard dependencies installed${NC}"

# ── 3. .env ──────────────────────────────────────────────────────────────
echo -e "${BOLD}[3/5] Checking environment file...${NC}"
if [ ! -f .env ]; then
  cp .env.example .env
  echo -e "${YELLOW}⚠  Created .env from .env.example — fill in your API keys!${NC}"
else
  echo -e "${GREEN}✓ .env already exists${NC}"
fi

# ── 4. Gmail OAuth ───────────────────────────────────────────────────────
echo -e "${BOLD}[4/5] Gmail authorisation...${NC}"
if [ -f gmail_credentials.json ]; then
  cd agent
  source .venv/bin/activate
  python -c "
import sys
sys.path.insert(0, '..')
from agent.email.gmail_service import authorize
authorize()
"
  cd ..
  echo -e "${GREEN}✓ Gmail authorised${NC}"
else
  echo -e "${YELLOW}⚠  gmail_credentials.json not found.${NC}"
  echo "   → Go to https://console.cloud.google.com"
  echo "   → Create a project → Enable Gmail API"
  echo "   → Credentials → OAuth 2.0 → Desktop app → Download JSON"
  echo "   → Save as gmail_credentials.json in this folder"
  echo "   → Re-run: ./setup.sh"
fi

# ── 5. Done ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/5] Setup complete!${NC}"
echo ""
echo -e "${BOLD}To start the agent:${NC}"
echo "  cd agent && source .venv/bin/activate"
echo "  uvicorn agent.main:app --reload --port 8000"
echo ""
echo -e "${BOLD}To start the dashboard (new terminal):${NC}"
echo "  cd dashboard && npm run dev"
echo ""
echo -e "${BOLD}Then open:${NC} http://localhost:3000"
echo ""
echo -e "${YELLOW}Don't forget to:${NC}"
echo "  1. Add ANTHROPIC_API_KEY to .env"
echo "  2. Upload your resume in Settings"
echo "  3. Configure job preferences in Settings → Job Preferences"
