"""
Agent-driven job sources.

  firecrawl      Firecrawl searches the web for each title x location, pulls
                 every result page as clean markdown, and Claude turns those
                 pages into structured job listings.

  agent_browser  The Stagehand browser agent opens company careers sites,
                 runs the search like a person would, and extracts the real
                 listings (instead of just a link to the search page).

Both feed the normal pipeline: dedupe -> batch scoring -> email drafts.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from agent.tools import firecrawl_client

logger = logging.getLogger(__name__)

FIRECRAWL_MAX_QUERIES = int(os.getenv("FIRECRAWL_MAX_QUERIES", "8"))
FIRECRAWL_RESULTS_PER_QUERY = int(os.getenv("FIRECRAWL_RESULTS_PER_QUERY", "6"))
AGENT_MAX_SITES = int(os.getenv("AGENT_MAX_SITES", "6"))

# Boards worth searching for AU roles; Firecrawl search is restricted to these
AU_JOB_DOMAINS = [
    "seek.com.au", "au.indeed.com", "au.linkedin.com", "linkedin.com",
    "au.jora.com", "glassdoor.com.au", "careers.vic.gov.au", "apsjobs.gov.au",
    "workforceaustralia.gov.au", "prosple.com", "gradconnection.com",
]
GLOBAL_JOB_DOMAINS = [
    "linkedin.com", "indeed.com", "glassdoor.com", "wellfound.com",
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com",
]


def _make_id(source: str, url: str, title: str = "") -> str:
    return hashlib.md5(f"{source}:{url}:{title}".encode()).hexdigest()


def _is_au(locations: list[str]) -> bool:
    keys = ("australia", "melbourne", "sydney", "brisbane", "perth", "adelaide",
            "hobart", "canberra", "vic", "nsw", "qld")
    return any(k in (l or "").lower() for l in locations for k in keys)


# ── Firecrawl ────────────────────────────────────────────────────────────────

def _build_queries(titles: list[str], locations: list[str], keywords: list[str]) -> list[str]:
    locs = [l for l in locations if l and l.lower() != "remote"] or ["Australia"]
    kw = " ".join(keywords[:2])
    queries = []
    for t in titles:
        for l in locs:
            queries.append(f"{t} jobs {l} {kw}".strip())
    if any((l or "").lower() == "remote" for l in locations):
        queries += [f"remote {t} jobs" for t in titles]
    # de-dupe, cap
    seen, out = set(), []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:FIRECRAWL_MAX_QUERIES]


async def firecrawl_job_search(
    titles: list[str], locations: list[str], keywords: list[str],
) -> list[dict]:
    if not titles:
        return []
    if not await firecrawl_client.is_available():
        logger.warning("Firecrawl isn't running (docker compose up -d) - skipping firecrawl source")
        return []

    au = _is_au(locations)
    domains = AU_JOB_DOMAINS if au else GLOBAL_JOB_DOMAINS
    queries = _build_queries(titles, locations, keywords)
    logger.info(f"Firecrawl: {len(queries)} queries across {len(domains)} job sites")

    sem = asyncio.Semaphore(3)

    async def _q(q: str) -> list[dict]:
        async with sem:
            return await firecrawl_client.search(
                q, limit=FIRECRAWL_RESULTS_PER_QUERY, scrape=True,
                country="au" if au else None, include_domains=domains,
            )

    batches = await asyncio.gather(*[_q(q) for q in queries], return_exceptions=True)
    pages: dict[str, dict] = {}
    for b in batches:
        if isinstance(b, list):
            for r in b:
                if r.get("markdown") and r["url"] not in pages:
                    pages[r["url"]] = r
    logger.info(f"Firecrawl: {len(pages)} unique pages scraped")
    if not pages:
        return []

    # Claude turns pages (single job ads and listing pages alike) into jobs
    page_list = list(pages.values())
    jobs: list[dict] = []
    for i in range(0, len(page_list), 4):
        chunk = page_list[i:i + 4]
        try:
            extracted = await asyncio.wait_for(
                asyncio.to_thread(_extract_jobs_from_pages, chunk, titles, locations), timeout=120,
            )
            jobs.extend(extracted)
        except Exception as e:
            logger.warning(f"Firecrawl page extraction failed: {e}")

    out = []
    for j in jobs:
        url = j.get("url") or ""
        out.append({
            "external_id": _make_id("firecrawl", url, j.get("title", "")),
            "title": j.get("title") or "Untitled role",
            "company": j.get("company") or (urlparse(url).netloc or "Unknown"),
            "location": j.get("location") or "",
            "description": (j.get("description") or "")[:4000],
            "url": url,
            "source": "firecrawl",
            "job_type": j.get("job_type") or None,
            "remote": bool(j.get("remote")),
            "salary_min": _num(j.get("salary_min")),
            "salary_max": _num(j.get("salary_max")),
            "posted_at": datetime.utcnow(),
            "is_referral_post": False,
        })
    logger.info(f"Firecrawl: {len(out)} jobs extracted")
    return out


def _num(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _extract_jobs_from_pages(pages: list[dict], titles: list[str], locations: list[str]) -> list[dict]:
    from agent.ai.claude_agent import client, MODEL
    blocks = []
    for n, p in enumerate(pages, 1):
        blocks.append(f"### PAGE {n}\nURL: {p['url']}\nTITLE: {p.get('title','')}\n\n{p['markdown'][:6000]}")
    prompt = (
        "These pages came from job sites. Extract every real job opening you can see.\n"
        f"Only keep roles relevant to any of: {', '.join(titles)}; located in or open to: "
        f"{', '.join(locations) or 'anywhere'}.\n"
        "For a single job ad page, return that job with the page URL. For a listing page, "
        "return each listing, using its own link if visible (make it absolute), otherwise the page URL.\n"
        "Skip ads, expired roles, and anything that is not a job.\n"
        "Return ONLY a JSON array of objects with keys: title, company, location, description "
        "(2-4 sentences: duties + key requirements), url, job_type, remote (bool), "
        "salary_min, salary_max (numbers or null). No markdown fences.\n\n" + "\n\n".join(blocks)
    )
    resp = client.messages.create(model=MODEL, max_tokens=4096,
                                  messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return [d for d in data if isinstance(d, dict) and d.get("title")] if isinstance(data, list) else []
    except json.JSONDecodeError:
        logger.warning(f"Could not parse extracted jobs: {raw[:200]}")
        return []


# ── Stagehand browser agent ──────────────────────────────────────────────────

class _Listing(BaseModel):
    title: str
    location: str = ""
    url: str = Field("", description="absolute link to the job posting, if visible")
    team: str = ""


class _ListingPage(BaseModel):
    jobs: list[_Listing] = Field(default_factory=list)


async def agent_browser_job_search(titles: list[str], locations: list[str]) -> list[dict]:
    """Visit company careers sites with the browser agent and pull real listings."""
    if not titles:
        return []
    from agent.scrapers.job_scraper import _get_companies_for_locations
    from agent.tools.browser_agent import BrowserAgent

    companies = _get_companies_for_locations(locations or [])
    if not companies:
        return []
    # Rotate through the list so each run covers different companies
    start = (datetime.utcnow().timetuple().tm_yday * AGENT_MAX_SITES) % len(companies)
    picked = (companies[start:] + companies[:start])[:AGENT_MAX_SITES]
    loc_hint = ", ".join(locations) or "any location"
    out: list[dict] = []

    try:
        async with BrowserAgent() as agent:
            for company, url_template in picked:
                for title in titles[:2]:
                    url = url_template.format(title=title.replace(" ", "+"))
                    try:
                        await agent.goto(url)
                        if agent.can_act:
                            # Cookie banners block results on many careers sites
                            await agent.act("if there is a cookie consent banner, reject non-essential "
                                            "cookies or close it; otherwise do nothing", timeout_s=20)
                        page = await agent.extract(
                            f"Extract every job listing shown in the search results that matches "
                            f"'{title}' in or near {loc_hint}. Include the link to each posting.",
                            _ListingPage,
                        )
                    except Exception as e:
                        logger.warning(f"Agent browse failed for {company}: {e}")
                        continue
                    for l in (page.jobs if page else [])[:15]:
                        link = l.url if l.url.startswith("http") else url
                        out.append({
                            "external_id": _make_id("agent_browser", link, f"{company}:{l.title}"),
                            "title": l.title,
                            "company": company,
                            "location": l.location or "",
                            "description": f"{l.title} at {company}" + (f" ({l.team})" if l.team else ""),
                            "url": link,
                            "source": "agent_browser",
                            "remote": "remote" in (l.location or "").lower(),
                            "posted_at": datetime.utcnow(),
                            "is_referral_post": False,
                        })
    except Exception as e:
        logger.warning(f"Browser agent unavailable: {e}")
    logger.info(f"Browser agent: {len(out)} listings from {len(picked)} careers sites")
    return out
