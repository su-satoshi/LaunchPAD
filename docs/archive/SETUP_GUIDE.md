# AI Job Pilot — Setup & Operations Guide

## What This Does

An autonomous AI agent that:
- **Searches** LinkedIn, Indeed, Glassdoor, Seek, Web3.careers, Prosple, AmbitionBox, ZipRecruiter, Google Jobs, and top-100 company career pages on a schedule you set
- **Matches** every job to your resume using Claude AI (scored 0–100%)
- **Drafts** personalised application emails and referral requests
- **Auto-sends** emails above your confidence threshold — everything else goes to draft for your review
- **Tracks** applications through a Kanban pipeline (applied → interview → offer)

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://python.org |
| Node.js | 18+ | https://nodejs.org |
| Git | any | https://git-scm.com |

---

## Step 1 — Get Your API Keys

### Anthropic (Claude AI) — Required
1. Go to https://console.anthropic.com
2. API Keys → Create Key
3. Copy the key (starts with `sk-ant-`)

### Gmail API — Required for email sending
1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "AI Job Pilot")
3. Enable the **Gmail API**: APIs & Services → Library → search "Gmail API" → Enable
4. Create credentials: APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
5. Application type: **Desktop app** → Name: "Job Pilot" → Create
6. Download the JSON → save as `gmail_credentials.json` in the project root
7. OAuth consent screen → Add yourself as a test user

---

## Step 2 — Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
GMAIL_FROM_ADDRESS=yourname@gmail.com
```

---

## Step 3 — Run Setup

```bash
./setup.sh
```

This will:
- Create Python virtualenv and install all backend packages
- Install Next.js dashboard packages
- Prompt you to authorise Gmail (browser will open)

---

## Step 4 — Start the Agent

**Terminal 1 — Backend:**
```bash
cd agent
source .venv/bin/activate
uvicorn agent.main:app --reload --port 8000
```

**Terminal 2 — Dashboard:**
```bash
cd dashboard
npm run dev
```

Open **http://localhost:3000**

---

## Step 5 — Configure in the Dashboard

### 5a. Upload Your Resume
- Go to **Settings → Profile**
- Click the upload area and select your PDF or TXT resume
- Claude will auto-extract your name, skills, work history, and experience

### 5b. Set Job Preferences
- Go to **Settings → Job Preferences**
- Add job titles: `Software Engineer`, `Backend Developer`, `Python Developer`
- Add keywords: `Python`, `FastAPI`, `AWS`, `TypeScript`
- Add exclude keywords: `10+ years`, `15+ years` (if you're not senior)
- Add locations: `Sydney`, `Melbourne`, `Remote`
- Tick the job sources you want to search

### 5c. Set Automation Rules
- Go to **Settings → Automation**
- **Min match score**: `0.6` — jobs below this are skipped
- **Auto-send threshold**: `0.85` — emails sent automatically if AI scores ≥ 85%
  - Set to `1.0` to always require manual review (safest to start)
- **Max applications/day**: `10`
- **Search frequency**: Every `6` hours

---

## Step 6 — First Run

Click **"Run Search Now"** on the Dashboard or Jobs page.

The agent will:
1. Search all configured sources for your job titles
2. Score each job against your resume (0–100%)
3. Draft personalised emails for matched jobs
4. Auto-send above your threshold or save to Drafts

---

## Dashboard Pages

| Page | What it shows |
|------|---------------|
| **Dashboard** | Live stats, top matches, agent status |
| **Jobs** | All found jobs with match scores, filterable by source/status |
| **Jobs → Detail** | Full job description, AI match reasons, skill gaps |
| **Emails** | Draft emails to review/edit/send, sent email history |
| **Applications** | Kanban pipeline (applied → interview → offer) |
| **Settings** | Profile, resume, job preferences, automation rules |

---

## Email Workflow

The agent creates three types of emails:
- **Application emails** — direct applications with personalised cover letters
- **Referral request emails** — asks a contact to refer you (from AmbitionBox/Glassdoor referral posts)
- **Follow-up emails** — auto-scheduled 7 days after sending an application

### Manual Review Flow
1. Go to **Emails** page
2. Click a draft to preview it
3. Edit the body or recipient if needed
4. Click **Send Now**

### Auto-Send Flow
Any job scoring ≥ your `auto_send_above_score` threshold where the agent finds an email address will be sent automatically during the search cycle.

---

## Production Deployment

### Backend (e.g. Railway, Render, DigitalOcean)
```bash
# Dockerfile for the agent
pip install -r agent/requirements.txt
uvicorn agent.main:app --host 0.0.0.0 --port 8000
```

Environment variables to set in production:
```
ANTHROPIC_API_KEY=...
DATABASE_URL=postgresql://...
GMAIL_CREDENTIALS_PATH=/app/gmail_credentials.json
GMAIL_TOKEN_PATH=/app/gmail_token.json
GMAIL_FROM_ADDRESS=...
ALLOWED_ORIGINS=https://your-dashboard.vercel.app
```

### Dashboard (Vercel)
```bash
cd dashboard
npx vercel --prod
```

Set `NEXT_PUBLIC_API_URL=https://your-agent.railway.app` in Vercel environment.

### Gmail on a Server
Before deploying, run `python -m agent.email.gmail_service` locally to generate `gmail_token.json`, then upload both `gmail_credentials.json` and `gmail_token.json` to your server/secrets store.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ANTHROPIC_API_KEY` error | Check `.env` has the correct key |
| Gmail auth fails | Delete `gmail_token.json` and re-run `./setup.sh` |
| No jobs found | Check preferences — job titles and sources must be set |
| Match scores all 0 | Ensure resume is uploaded in Settings |
| `python-jobspy` import error | Run `pip install python-jobspy` in the venv |
| Port 8000 in use | Change to `--port 8001` and update `NEXT_PUBLIC_API_URL` |
| CORS error in dashboard | Add your frontend URL to `ALLOWED_ORIGINS` in `.env` |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Next.js Dashboard              │
│  /jobs  /emails  /applications  /settings        │
└───────────────────┬─────────────────────────────┘
                    │ HTTP (proxied via next.config)
┌───────────────────▼─────────────────────────────┐
│                FastAPI Backend                   │
│  /api/jobs  /api/emails  /api/settings           │
├─────────────────────────────────────────────────┤
│  APScheduler  →  Search Cycle (every N hours)   │
│    ├── Scrapers: jobspy, seek, web3, prosple…   │
│    ├── Claude AI: match + email draft           │
│    └── Gmail API: auto-send or save draft       │
├─────────────────────────────────────────────────┤
│  SQLite / PostgreSQL (SQLAlchemy)               │
└─────────────────────────────────────────────────┘
```

---

## File Structure

```
AI job pilot/
├── agent/                    # Python FastAPI backend
│   ├── main.py               # App entry point + scheduler startup
│   ├── scheduler.py          # Orchestrates full search cycle
│   ├── requirements.txt
│   ├── models/
│   │   └── database.py       # SQLAlchemy models
│   ├── scrapers/
│   │   └── job_scraper.py    # All job board scrapers
│   ├── ai/
│   │   └── claude_agent.py   # Claude AI: match, draft, analyze
│   ├── email/
│   │   └── gmail_service.py  # Gmail API integration
│   └── routers/
│       ├── jobs.py
│       ├── emails.py
│       ├── applications.py
│       └── settings.py
├── dashboard/                # Next.js 14 frontend
│   └── src/app/
│       ├── page.tsx          # Dashboard home
│       ├── jobs/             # Job listings + detail
│       ├── emails/           # Email drafts + management
│       ├── applications/     # Kanban pipeline
│       └── settings/         # Profile + preferences
├── .env.example
├── setup.sh
└── SETUP_GUIDE.md
```
