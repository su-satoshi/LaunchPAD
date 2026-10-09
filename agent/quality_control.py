"""
Post-search quality control. Runs automatically after every search cycle (and
on its own timer), no clicks needed.

For every job you haven't acted on yet it cross-checks:
  1. Criteria   - excluded keywords, wrong job type, below your current minimum
                  match score (e.g. after you raise it)
  2. Freshness  - posted (or first seen) longer ago than QC_MAX_AGE_DAYS
  3. Duplicates - the same role at the same company found on several boards;
                  the best-scored copy is kept
  4. Liveness   - the link is dead (404/410/unreachable) or the page says the
                  role is closed / filled / no longer accepting applications
And for forum referral drafts:
  5. Stale or deleted threads, and posts that say the role is filled

Nothing is deleted. Jobs are marked `expired` (gone / old / closed) or
`skipped` (doesn't match criteria) with the reason in `qc_reason`, and their
unsent email drafts are archived. Jobs you've emailed, applied to, or moved
along the pipeline are never touched.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import timedelta
from typing import Optional

import httpx
from sqlalchemy import or_

from agent.models.database import (
    ApplicationStatus, Email, ForumPost, Job, JobPreferences, SessionLocal,
)
from agent.utils import is_public_url, safe_http_url, utcnow

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = int(os.getenv("QC_MAX_AGE_DAYS", "30"))
THREAD_MAX_AGE_DAYS = int(os.getenv("QC_THREAD_MAX_AGE_DAYS", "14"))
RECHECK_HOURS = int(os.getenv("QC_RECHECK_HOURS", "24"))
MAX_PAGE_CHECKS = int(os.getenv("QC_MAX_PAGE_CHECKS", "150"))

# Jobs QC may change. Anything further along the pipeline is yours and left alone.
OPEN_STATUSES = (ApplicationStatus.found, ApplicationStatus.matched, ApplicationStatus.draft_ready)

# Phrases job boards use when a listing is closed. Checked case-insensitively.
CLOSED_PATTERNS = re.compile(
    r"no longer (?:accepting|taking) applications"
    r"|(?:this|the) (?:job|position|role|listing|vacancy|posting|ad) (?:has|is) (?:expired|closed|been filled|no longer available)"
    r"|(?:job|position|role|listing|vacancy|posting) (?:is )?no longer (?:available|open|active)"
    r"|applications? (?:are |is |have )?(?:now )?closed"
    r"|position (?:has been )?filled"
    r"|this job is closed"
    r"|job not found|page not found|listing not found"
    r"|we couldn.t find (?:that|this) job",
    re.IGNORECASE,
)
FILLED_THREAD_PATTERNS = re.compile(
    r"\[deleted\]|\[removed\]|(?:role|position|spot)s? (?:has been |have been |is |are )?(?:filled|closed)"
    r"|no longer hiring|not hiring anymore|hiring is closed|update:\s*filled",
    re.IGNORECASE,
)

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

_lock = asyncio.Lock()
_last: dict = {"ran_at": None, "result": None}


def last_result() -> dict:
    return {**_last, "running": _lock.locked()}


# ── helpers ──────────────────────────────────────────────────────────────────

def _norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    kw = _norm(keyword)
    return bool(kw) and re.search(rf"\b{re.escape(kw)}\b", text) is not None


def _expire(job: Job, reason: str, status: ApplicationStatus = ApplicationStatus.expired) -> None:
    job.status = status
    job.qc_reason = reason[:300]


async def _fetch_page(client: httpx.AsyncClient, url: str) -> tuple[Optional[int], str]:
    """Return (status_code, first ~200KB of text). (None, '') when unreachable or not public."""
    if not await is_public_url(url):
        return None, ""
    try:
        async with client.stream("GET", url) as resp:
            # Redirected to an internal address? treat as unreachable
            if not await is_public_url(str(resp.url)):
                return None, ""
            chunks, size = [], 0
            async for chunk in resp.aiter_text():
                chunks.append(chunk)
                size += len(chunk)
                if size > 200_000:
                    break
            return resp.status_code, "".join(chunks)
    except Exception:
        return None, ""


def _page_says_closed(html: str) -> bool:
    # Strip tags cheaply; good enough for phrase matching
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return bool(CLOSED_PATTERNS.search(text[:150_000]))


# ── the pass ─────────────────────────────────────────────────────────────────

async def run_quality_control(check_pages: bool = True) -> dict:
    """Run every QC check. Safe to call any time; concurrent calls are skipped."""
    if _lock.locked():
        return {"skipped": "already running"}
    async with _lock:
        started = utcnow()
        counts = {"criteria": 0, "old": 0, "duplicate": 0, "dead_link": 0, "closed": 0,
                  "bad_link": 0, "threads_expired": 0, "drafts_archived": 0, "pages_checked": 0}
        db = SessionLocal()
        try:
            prefs = db.query(JobPreferences).first()
            open_jobs = db.query(Job).filter(Job.status.in_(OPEN_STATUSES)).all()

            # 1-3. Deterministic checks (no network)
            excluded = [k for k in (getattr(prefs, "exclude_keywords", None) or []) if k and k.strip()]
            wanted_types = {_norm(t).replace(" ", "") for t in (getattr(prefs, "job_types", None) or []) if t}
            min_score = getattr(prefs, "min_match_score", None)
            age_cutoff = started - timedelta(days=MAX_AGE_DAYS)
            best_by_key: dict[tuple[str, str], Job] = {}

            for job in open_jobs:
                if not safe_http_url(job.url):
                    _expire(job, "Missing or unsafe link")
                    counts["bad_link"] += 1
                    continue
                title_desc = _norm(f"{job.title} {job.description}")
                hit = next((k for k in excluded if _contains_keyword(title_desc, k)), None)
                if hit:
                    _expire(job, f"Contains excluded keyword '{hit}'", ApplicationStatus.skipped)
                    counts["criteria"] += 1
                    continue
                jtype = _norm(job.job_type).replace(" ", "")
                if wanted_types and jtype and not any(t in jtype or jtype in t for t in wanted_types):
                    _expire(job, f"Job type '{job.job_type}' isn't one you selected", ApplicationStatus.skipped)
                    counts["criteria"] += 1
                    continue
                if min_score and job.match_score is not None and job.match_score < min_score \
                        and job.status != ApplicationStatus.found:
                    _expire(job, f"Match {job.match_score:.0%} is below your minimum {min_score:.0%}",
                            ApplicationStatus.skipped)
                    counts["criteria"] += 1
                    continue
                seen = job.posted_at or job.found_at
                if seen and seen < age_cutoff and job.source != "top_companies":
                    _expire(job, f"Posted more than {MAX_AGE_DAYS} days ago")
                    counts["old"] += 1
                    continue
                key = (_norm(job.title), _norm(job.company))
                if key[0] and key[1]:
                    keep = best_by_key.get(key)
                    if keep is None:
                        best_by_key[key] = job
                    else:
                        # A real job ad always beats a company search-page link; then higher score wins
                        def rank(j: Job) -> tuple:
                            return (j.source != "top_companies", j.match_score or 0)
                        loser = job if rank(job) <= rank(keep) else keep
                        winner = keep if loser is job else job
                        _expire(loser, f"Duplicate of the same role on {winner.source or 'another board'}")
                        best_by_key[key] = winner
                        counts["duplicate"] += 1
            db.commit()

            # 4. Liveness: link status + "this job is closed" text, most relevant first
            if check_pages:
                recheck_before = started - timedelta(hours=RECHECK_HOURS)
                to_check = (db.query(Job)
                            .filter(Job.status.in_(OPEN_STATUSES),
                                    Job.source != "top_companies",   # these are search pages, not ads
                                    or_(Job.qc_checked_at.is_(None), Job.qc_checked_at < recheck_before))
                            .order_by(Job.match_score.desc().nullslast())
                            .limit(MAX_PAGE_CHECKS).all())
                if to_check:
                    sem = asyncio.Semaphore(12)
                    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=_UA,
                                                 limits=httpx.Limits(max_connections=12)) as client:
                        async def _one(job_id: int, url: str):
                            async with sem:
                                return job_id, await _fetch_page(client, url)
                        results = await asyncio.gather(*[_one(j.id, j.url) for j in to_check])
                    by_id = {j.id: j for j in to_check}
                    for job_id, (code, body) in results:
                        job = by_id[job_id]
                        job.qc_checked_at = started
                        counts["pages_checked"] += 1
                        if code in (404, 410) or code is None:
                            # Unreachable once could be a blip: expire only on a clear 404/410,
                            # or when it was already unreachable on the previous check.
                            if code in (404, 410) or job.url_valid is False:
                                _expire(job, "Link is dead (job ad removed)")
                                job.url_valid = False
                                counts["dead_link"] += 1
                            else:
                                job.url_valid = False
                            continue
                        job.url_valid = code < 400
                        # 401/403 = sign-in / bot wall: can't read it, leave it alone
                        if code < 400 and body and _page_says_closed(body):
                            _expire(job, "The posting says it's closed or filled")
                            counts["closed"] += 1
                    db.commit()

            # Archive unsent drafts for anything QC removed
            removed_ids = [j for (j,) in db.query(Job.id).filter(
                Job.status.in_([ApplicationStatus.expired, ApplicationStatus.skipped]),
                Job.qc_reason.isnot(None))]
            if removed_ids:
                counts["drafts_archived"] = db.query(Email).filter(
                    Email.job_id.in_(removed_ids), Email.status == "draft"
                ).update({"status": "archived"}, synchronize_session=False)
                db.commit()

            # 5. Forum referral drafts
            thread_cutoff = started - timedelta(days=THREAD_MAX_AGE_DAYS)
            stale = db.query(ForumPost).filter(
                ForumPost.status == "draft", ForumPost.kind != "open_to_work",
                ForumPost.created_at < thread_cutoff,
            ).update({"status": "expired", "error_message": f"Thread is older than {THREAD_MAX_AGE_DAYS} days"},
                     synchronize_session=False)
            counts["threads_expired"] += stale
            for post in db.query(ForumPost).filter(ForumPost.status == "draft",
                                                   ForumPost.kind != "open_to_work").all():
                if post.thread_snippet and FILLED_THREAD_PATTERNS.search(post.thread_snippet):
                    post.status = "expired"
                    post.error_message = "The thread says the role is filled or the post was removed"
                    counts["threads_expired"] += 1
            if check_pages:
                drafts = db.query(ForumPost).filter(ForumPost.status == "draft",
                                                    ForumPost.kind != "open_to_work",
                                                    ForumPost.thread_url.isnot(None)).limit(60).all()
                if drafts:
                    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=_UA) as client:
                        pages = await asyncio.gather(*[_fetch_page(client, p.thread_url) for p in drafts])
                    for post, (code, body) in zip(drafts, pages, strict=True):
                        if code in (404, 410) or (code and code < 400 and FILLED_THREAD_PATTERNS.search(body[:100_000])):
                            post.status = "expired"
                            post.error_message = "Thread was deleted, or the role is filled"
                            counts["threads_expired"] += 1
            db.commit()

            removed = sum(v for k, v in counts.items() if k not in ("pages_checked", "drafts_archived"))
            result = {**counts, "removed_total": removed,
                      "duration_s": round((utcnow() - started).total_seconds(), 1)}
            _last.update(ran_at=started.isoformat(), result=result)
            logger.info(f"Quality control: {result}")
            return result
        except Exception as e:
            db.rollback()
            logger.exception(f"Quality control failed: {e}")
            return {"error": str(e)}
        finally:
            db.close()
