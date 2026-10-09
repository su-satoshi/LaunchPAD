"""
Thin async client for the self-hosted Firecrawl API (docker-compose.yml).

No Firecrawl account or API key is needed: the bundled stack runs with
USE_DB_AUTHENTICATION=false. FIRECRAWL_API_KEY is only sent if you point
FIRECRAWL_URL at an instance that requires one.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FIRECRAWL_URL = os.getenv("FIRECRAWL_URL", "http://localhost:3002").rstrip("/")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Cache the health check so a stopped stack doesn't add a timeout to every call
_health: dict[str, Any] = {"ok": None, "checked_at": 0.0}
_HEALTH_TTL_S = 60


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if FIRECRAWL_API_KEY:
        h["Authorization"] = f"Bearer {FIRECRAWL_API_KEY}"
    return h


async def is_available(force: bool = False) -> bool:
    """True if the self-hosted Firecrawl API answers."""
    now = time.monotonic()
    if not force and _health["ok"] is not None and now - _health["checked_at"] < _HEALTH_TTL_S:
        return bool(_health["ok"])
    ok = False
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            # Self-hosted Firecrawl answers on / and on its queue health route.
            for path in ("/", "/v0/health/liveness"):
                try:
                    r = await client.get(f"{FIRECRAWL_URL}{path}")
                    if r.status_code < 500:
                        ok = True
                        break
                except httpx.HTTPError:
                    continue
    except Exception:
        ok = False
    _health.update(ok=ok, checked_at=now)
    return ok


async def search(
    query: str,
    limit: int = 8,
    *,
    scrape: bool = True,
    country: str | None = None,
    include_domains: list[str] | None = None,
    timeout_s: float = 90.0,
) -> list[dict]:
    """
    Web search through Firecrawl (backed by the bundled SearXNG).
    With scrape=True each result also carries the page as markdown.
    Returns a list of {url, title, description, markdown}.
    """
    payload: dict[str, Any] = {"query": query, "limit": max(1, min(limit, 20))}
    if country:
        payload["country"] = country
    if include_domains:
        payload["includeDomains"] = include_domains
    if scrape:
        payload["scrapeOptions"] = {"formats": ["markdown"], "onlyMainContent": True}

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(f"{FIRECRAWL_URL}/v2/search", json=payload, headers=_headers())
            if r.status_code == 400 and include_domains:
                # Older builds don't know includeDomains - fall back to site: operators
                payload.pop("includeDomains", None)
                sites = " OR ".join(f"site:{d}" for d in include_domains)
                payload["query"] = f"{query} ({sites})"
                r = await client.post(f"{FIRECRAWL_URL}/v2/search", json=payload, headers=_headers())
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        logger.warning(f"Firecrawl search failed for '{query}': {e}")
        return []

    data = body.get("data") or {}
    # v2 returns {"web": [...], "news": [...]}; v1 returned a flat list
    items = data.get("web", []) if isinstance(data, dict) else data
    results = []
    for it in items or []:
        meta = it.get("metadata") or {}
        results.append({
            "url": it.get("url") or meta.get("sourceURL") or meta.get("url") or "",
            "title": it.get("title") or meta.get("title") or "",
            "description": it.get("description") or meta.get("description") or "",
            "markdown": it.get("markdown") or "",
        })
    return [r for r in results if r["url"]]


async def scrape(url: str, *, wait_ms: int = 0, timeout_s: float = 60.0) -> dict:
    """Scrape one URL to markdown. Returns {url, title, markdown} or {} on failure."""
    payload: dict[str, Any] = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
    if wait_ms:
        payload["waitFor"] = wait_ms
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(f"{FIRECRAWL_URL}/v2/scrape", json=payload, headers=_headers())
            r.raise_for_status()
            data = (r.json() or {}).get("data") or {}
    except Exception as e:
        logger.warning(f"Firecrawl scrape failed for {url}: {e}")
        return {}
    meta = data.get("metadata") or {}
    return {"url": url, "title": meta.get("title", ""), "markdown": data.get("markdown") or ""}


async def scrape_many(urls: list[str], concurrency: int = 3) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(u: str) -> dict:
        async with sem:
            return await scrape(u)

    results = await asyncio.gather(*[_one(u) for u in urls], return_exceptions=True)
    return [r for r in results if isinstance(r, dict) and r.get("markdown")]
