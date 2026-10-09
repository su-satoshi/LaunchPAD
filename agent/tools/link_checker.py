"""HEAD-checks job links and records which ones are dead. Used after each search and from the Jobs page."""
from __future__ import annotations

import asyncio
import logging

import httpx

from agent.models.database import Job, SessionLocal
from agent.utils import is_public_url

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/1.0)"}


async def _check(client: httpx.AsyncClient, sem: asyncio.Semaphore, job_id: int, url: str) -> tuple[int, bool]:
    async with sem:
        # Never probe localhost / LAN addresses that came in through scraped data
        if not await is_public_url(url):
            return job_id, False
        try:
            resp = await client.head(url)
            if resp.status_code in (403, 405):          # some sites reject HEAD
                resp = await client.get(url, headers={"Range": "bytes=0-0"})
            return job_id, resp.status_code < 400
        except Exception:
            return job_id, False


async def verify_unchecked_links(limit: int = 300, concurrency: int = 20) -> dict:
    """Check up to `limit` jobs whose links haven't been verified. Returns counts."""
    db = SessionLocal()
    try:
        rows = (db.query(Job.id, Job.url)
                .filter(Job.url.isnot(None), Job.url != "", Job.url_valid.is_(None))
                .limit(limit).all())
        if not rows:
            return {"checked": 0, "valid": 0, "broken": 0}

        sem = asyncio.Semaphore(concurrency)
        # One pooled client instead of a new connection pool per link
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=_UA,
                                     limits=httpx.Limits(max_connections=concurrency)) as client:
            results = await asyncio.gather(*[_check(client, sem, jid, url) for jid, url in rows])

        valid = [jid for jid, ok in results if ok]
        broken = [jid for jid, ok in results if not ok]
        if valid:
            db.query(Job).filter(Job.id.in_(valid)).update({"url_valid": True}, synchronize_session=False)
        if broken:
            db.query(Job).filter(Job.id.in_(broken)).update({"url_valid": False}, synchronize_session=False)
        db.commit()
        logger.info(f"Link verify: {len(valid)} valid, {len(broken)} broken")
        return {"checked": len(results), "valid": len(valid), "broken": len(broken)}
    except Exception as e:
        logger.error(f"Link verification failed: {e}")
        db.rollback()
        return {"checked": 0, "valid": 0, "broken": 0, "error": str(e)}
    finally:
        db.close()
