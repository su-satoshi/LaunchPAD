# LaunchPAD - Orion AI job engine

An AI agent that finds jobs, scores them against your resume, drafts applications, and works the referral forums for you. Everything runs on your own machine from this one repo. The only API key it needs is Anthropic's.

| Piece | What it does | Where |
| --- | --- | --- |
| **Dashboard** | Next.js UI: overview, jobs, referrals, emails, applications, settings | `dashboard/` |
| **Agent backend** | FastAPI + scheduler: scrape → dedupe → Claude batch scoring → email drafts | `agent/` |
| **Firecrawl (self-hosted)** | Web search + clean page scraping, built from source at a pinned tag | `docker-compose.yml` |
| **Stagehand browser agent** | Agent-first browser (Browserbase's open-source SDK), running locally on your Chrome | `agent/tools/browser_agent.py` |
| **Referral agent** | Finds hiring / referral posts on Reddit, LinkedIn and Glassdoor, drafts replies and open-to-work posts | `agent/referrals/` |

You don't need a Firecrawl or Browserbase account. Firecrawl runs in Docker with auth turned off. Stagehand's Python SDK launches your installed Google Chrome and uses your Anthropic key to understand pages.

## Quick start

Requirements: Python 3.11+, Node 18+, Google Chrome, Docker Desktop (for Firecrawl).

```bash
./setup.sh          # venv, pip + npm installs, .env
# put your key in .env  ->  ANTHROPIC_API_KEY=sk-ant-...
./start.sh          # Firecrawl (docker), backend :8000, dashboard :3000
```

The first `docker compose up` builds Firecrawl from source, which takes about 10 minutes. After that it starts in seconds. The app works without it: the Firecrawl source is skipped and shows as "Not running" in Settings → API Usage.

## How a search run works

1. **Settings → Search criteria**: set titles, locations and keywords, then tick the sources you want. Two of them are new:
   - **Firecrawl (web)**: searches the big AU job boards (Seek, Indeed, LinkedIn, Jora, APS Jobs and more) through the self-hosted Firecrawl and SearXNG. It scrapes every result page to markdown, and Claude pulls out the real listings.
   - **Agent Browser**: the Stagehand agent opens company careers sites, dismisses cookie banners, and extracts the actual openings. Before, these were just links to a search page. It covers a rotating set of companies each run (`AGENT_MAX_SITES`).
2. **Run Search**: results are deduped and batch-scored against your resume. Matching jobs get email drafts, and a copy goes to your Gmail Drafts folder once Gmail is connected.
3. **Quality control runs by itself** when the search finishes, and again every 12 hours (see below).
4. If **Referrals → My details → "Find threads on every search run"** is on, the run also searches the forums and drafts replies. **Nothing is ever posted automatically.**

## Automatic quality control

After every search, with no clicks needed, `agent/quality_control.py` goes through every job you haven't acted on yet and removes:

| Check | Removed when |
| --- | --- |
| Criteria | it contains an excluded keyword, has a job type you didn't pick, or scores below your current minimum (e.g. after you raise it) |
| Freshness | it was posted, or first seen, more than `QC_MAX_AGE_DAYS` (30) days ago |
| Duplicates | the same role at the same company turned up on several boards. It keeps one copy: a real job ad beats a company search-page link, then the higher score wins |
| Dead links | the posting returns 404/410, or is unreachable on two checks in a row |
| Closed ads | the page says "no longer accepting applications", "position filled", "this job has expired" and similar |
| Referral threads | forum drafts older than 14 days, or threads that were deleted or say the role is filled |

Nothing is deleted. Removed jobs are marked **expired** (gone, old, closed or duplicate) or **skipped** (outside your criteria), with the reason shown when you hover the status on the Jobs page. Their unsent email drafts are archived. Jobs you've emailed, applied to or moved along the pipeline are never touched. The Jobs list hides expired and skipped jobs; choose them in the status filter to see them. The search panel shows what the check removed.

## Referrals

The Referrals page has three tabs:

- **Request referrals**: the existing flow. It emails people at companies you've matched with.
- **My details**: what the agent says about you. Empty fields fall back to your parsed resume and job preferences, and each one is labelled *From resume*, *From preferences* or *Missing*. Type in a field to override it. Privacy switches control whether your email, phone and LinkedIn may appear in public posts. Phone and email are off by default.
- **Forum posts**:
  - **Accounts**: opens a visible Chrome window on the agent's profile so you can sign in to Reddit, LinkedIn or Glassdoor yourself. The agent never sees your password; only the browser cookies are kept in `.browser-data/`.
  - **Find hiring & referral posts**: Firecrawl and the browser agent look for posts where people are hiring or offering referrals for your target roles. Claude scores how well each one fits you and drafts a reply.
  - **Draft my open-to-work posts**: writes a "looking for a referral" post for each platform, and for each subreddit you listed.
  - Edit any draft, then **Approve & post**. The browser agent posts it from your signed-in profile in a visible window, checks that it appeared, and marks it Posted or Failed with the reason.

### Use it responsibly

Reddit, LinkedIn and Glassdoor all prohibit automated or bulk posting in their terms, and accounts that post too often get flagged or banned. That's why every post needs your approval, there's a per-platform daily cap (default 5), and replies only go to posts that score as a real fit. Read each subreddit's rules before posting; many ban "hire me" posts outside their weekly threads. You're responsible for what's posted from your accounts.

## Security model

LaunchPAD has no login. It's built to run only on your own computer:

- **Local only.** The backend, dashboard and Firecrawl all listen on `127.0.0.1`, so nothing is reachable from your Wi-Fi or uni network.
- **Request guard.** The API rejects requests with an unexpected `Host` header (DNS rebinding) and state-changing requests from other websites (`Origin` / `Sec-Fetch-Site`). Without this, any page you visit could quietly tell the API to send an email or approve a forum post.
- **Untrusted scraped data.** Job links and forum threads come from the open web:
  - Only `http(s)` links are stored or rendered.
  - The backend won't fetch localhost, LAN or cloud-metadata addresses, including after a redirect (SSRF).
  - Every prompt that includes scraped text tells Claude to treat it as data, not instructions.
- **Your credentials.**
  - Auto-apply checks the real hostname before typing a portal password, so a look-alike link can't collect it.
  - Your Gmail token and saved browser sessions are written readable by you only.
  - Forum sign-ins happen in a real Chrome window; the agent never sees your password.
- **Email safety.**
  - Header values are stripped of line breaks (no header injection), and HTML is escaped.
  - An email can't be sent twice.
  - Auto-send never goes to an address the model guessed.

## Development

```bash
pip install -r requirements-dev.txt
ruff check agent tests && pytest -q              # backend lint + 42 tests
cd dashboard && npm run typecheck && npm run build
```

CI (`.github/workflows/ci.yml`) runs the same checks on every push, plus `pip-audit`, `npm audit` and a gitleaks secret scan.

**Upgrading from an earlier checkout:** the dashboard moved to Next.js 15 / React 19 (security fixes) and several Python packages were upgraded. After pulling, run `./setup.sh` again, or run `pip install -r agent/requirements.txt` and `cd dashboard && npm install`. Database changes apply automatically on the next start.

## Configuration

See `.env.example`. The main settings:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | — | Required. Used for matching, drafting and Stagehand. |
| `FIRECRAWL_URL` | `http://localhost:3002` | Self-hosted Firecrawl API |
| `FIRECRAWL_REF` | `v2.11.498` | Firecrawl release that `docker-compose.yml` builds |
| `STAGEHAND_MODEL` | `anthropic/claude-sonnet-4-6` | Model the browser agent uses |
| `CHROME_PATH` | auto | Path to Chrome, if auto-detect fails |
| `AGENT_HEADLESS` / `POST_HEADLESS` | `true` / `false` | Search in the background; post in a visible window |
| `QC_MAX_AGE_DAYS` | `30` | Quality control hides job ads older than this |
| `QC_RECHECK_HOURS` / `QC_MAX_PAGE_CHECKS` | `24` / `150` | How often, and how many, postings QC re-opens per run |

## Architecture

```
dashboard (Next.js :3000)  ──/api──▶  agent (FastAPI :8000)
                                         ├─ scheduler: scrape → dedupe → score → draft → quality control
                                         │    ├─ jobspy / Seek / custom scrapers
                                         │    ├─ firecrawl source ──▶ Firecrawl :3002 (docker)
                                         │    │                         ├─ SearXNG (search)
                                         │    │                         └─ Playwright service
                                         │    └─ agent_browser source ─┐
                                         ├─ referral agent ────────────┤
                                         │    discover → draft → approve → post
                                         └─ Stagehand browser agent ◀──┘
                                              your Chrome + .browser-data profile
```

## Licences

Firecrawl is AGPL-3.0. It's built from its upstream source and run as a separate service, not copied into this repo. Stagehand is MIT. Keep this repo private, or follow the AGPL terms, if you modify and distribute Firecrawl.
