import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, or_, text
from sqlalchemy.orm import Session

from agent.models.database import get_db, Job, Application, Email, UserProfile, ApplicationStatus
from agent.scheduler import run_search_cycle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT: All fixed-path routes MUST come before /{job_id} wildcard routes.
# FastAPI/Starlette matches in declaration order; a parameterised route will
# absorb paths like /bulk-apply before the specific handler is reached.
# ─────────────────────────────────────────────────────────────────────────────


@router.get("")
def list_jobs(
    status: Optional[str] = None,
    source: Optional[str] = None,
    min_score: Optional[float] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    if source:
        q = q.filter(Job.source == source)
    if min_score is not None:
        q = q.filter(Job.match_score >= min_score)
    if search:
        q = q.filter(or_(
            Job.title.ilike(f"%{search}%"),
            Job.company.ilike(f"%{search}%"),
        ))
    total = q.count()
    jobs = q.order_by(desc(Job.match_score), desc(Job.found_at)).offset((page - 1) * limit).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "jobs": [_job_dict(j) for j in jobs]}


# ── Fixed-path POST / GET routes (before wildcard) ───────────────────────────

@router.post("/search/trigger")
async def trigger_search():
    """Kick off a job search cycle in the background and return immediately."""
    from agent.scheduler import is_search_running
    if is_search_running():
        return {"ok": True, "status": "already_running"}

    async def _run():
        from agent.models.database import SessionLocal
        db = SessionLocal()
        try:
            await run_search_cycle(db)
        finally:
            db.close()

    asyncio.create_task(_run())
    return {"ok": True, "status": "search started"}


@router.get("/search/status")
def search_status(db: Session = Depends(get_db)):
    """Check if a search is running + current run progress."""
    from agent.scheduler import is_search_running
    from agent.models.database import SearchRun
    is_running = is_search_running()
    latest = db.query(SearchRun).order_by(SearchRun.id.desc()).first()
    jobs_committed = 0
    jobs_matched   = 0
    jobs_found     = 0
    if latest:
        jobs_found = latest.jobs_found or 0
        from sqlalchemy import func
        jobs_committed = db.query(func.count(Job.id)).filter(
            Job.found_at >= latest.started_at
        ).scalar() or 0
        jobs_matched = db.query(func.count(Job.id)).filter(
            Job.found_at >= latest.started_at,
            Job.match_score >= 0.5
        ).scalar() or 0
    return {
        "is_running": is_running,
        "jobs_found": jobs_found,
        "jobs_scored": jobs_committed,
        "jobs_matched": jobs_matched,
    }


@router.get("/stats/summary")
def job_stats(db: Session = Depends(get_db)):
    total = db.query(Job).count()
    matched = db.query(Job).filter(Job.match_score >= 0.7).count()
    applied = db.query(Job).filter(Job.status == ApplicationStatus.email_sent).count()
    by_source = db.execute(
        text("SELECT source, COUNT(*) as count FROM jobs GROUP BY source")
    ).fetchall()
    by_status = db.execute(
        text("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
    ).fetchall()
    return {
        "total_found": total,
        "total_matched": matched,
        "total_applied": applied,
        "by_source": {r[0]: r[1] for r in by_source},
        "by_status": {r[0]: r[1] for r in by_status},
    }


# ── Link verification ─────────────────────────────────────────────────────────

@router.post("/verify-links")
async def verify_links(db: Session = Depends(get_db)):
    """
    Background-safe: HEAD-checks all job URLs that haven't been verified yet.
    Marks url_valid=True/False on each job. Returns counts.
    """
    jobs_to_check = db.query(Job).filter(
        Job.url.isnot(None),
        Job.url != "",
        Job.url_valid.is_(None),
    ).limit(200).all()

    if not jobs_to_check:
        return {"checked": 0, "valid": 0, "broken": 0}

    async def _check(job: Job) -> tuple[int, bool]:
        try:
            async with httpx.AsyncClient(
                timeout=8,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JobPilot/1.0)"},
            ) as client:
                resp = await client.head(job.url)
                # Some sites reject HEAD — fall back to GET with a tiny range
                if resp.status_code in (405, 403):
                    resp = await client.get(job.url, headers={"Range": "bytes=0-0"})
                return (job.id, resp.status_code < 400)
        except Exception:
            return (job.id, False)

    results = await asyncio.gather(*[_check(j) for j in jobs_to_check])

    valid_ids = {jid for jid, ok in results if ok}
    broken_ids = {jid for jid, ok in results if not ok}

    db.query(Job).filter(Job.id.in_(valid_ids)).update({"url_valid": True}, synchronize_session=False)
    db.query(Job).filter(Job.id.in_(broken_ids)).update({"url_valid": False}, synchronize_session=False)
    db.commit()

    return {"checked": len(results), "valid": len(valid_ids), "broken": len(broken_ids)}


# ── Bulk import from URL ──────────────────────────────────────────────────────

class BulkApplyRequest(BaseModel):
    url: str
    dry_run: bool = False


@router.post("/bulk-apply")
async def bulk_apply_from_url(req: BulkApplyRequest, db: Session = Depends(get_db)):
    """
    Fetch a webpage of job listings, extract them via Claude, score them
    against the user's resume, persist to DB, and draft application emails.
    """
    import re
    import json as json_lib
    import anthropic as _anthropic
    import os
    from dotenv import dotenv_values
    from agent.ai.claude_agent import batch_match_jobs, draft_application_email

    profile = db.query(UserProfile).first()
    if not profile or not profile.resume_text:
        raise HTTPException(400, "Upload your resume first in Settings → Profile")

    # ── 1. Fetch the page (httpx first, Playwright fallback for JS-rendered) ─
    async def _fetch_with_playwright(url: str) -> str:
        """Render the page in a real Chromium browser and return its text."""
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    )
                )
                page = await ctx.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                # Wait extra half-second for late JS renders
                await page.wait_for_timeout(500)
                html = await page.content()
                await browser.close()
            sp = BeautifulSoup(html, "html.parser")
            for tag in sp(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                tag.decompose()
            return sp.get_text(separator="\n", strip=True)
        except Exception as e:
            logger.warning(f"Playwright render failed: {e}")
            return ""

    page_text = ""
    try:
        async with httpx.AsyncClient(
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
            follow_redirects=True,
        ) as client:
            resp = await client.get(req.url)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
            tag.decompose()
        page_text = soup.get_text(separator="\n", strip=True)[:12_000]
    except httpx.HTTPStatusError as e:
        raise HTTPException(400, f"Page returned HTTP {e.response.status_code}: {req.url}")
    except Exception as e:
        raise HTTPException(400, f"Could not fetch URL: {e}")

    # ── 2. Playwright fallback for JS-rendered pages ─────────────────────────
    #      Detect JS-rendered pages: short text, or known JS-heavy portals
    JS_PORTALS = ("amazon.jobs", "linkedin.com/jobs", "seek.com.au", "indeed.com",
                  "glassdoor.com", "workday.com", "greenhouse.io", "lever.co",
                  "smartrecruiters.com", "workable.com", "icims.com", "myworkdayjobs")
    is_js_portal = any(p in req.url for p in JS_PORTALS)

    if len(page_text.strip()) < 300 or is_js_portal:
        logger.info(f"Falling back to Playwright for: {req.url}")
        page_text = await _fetch_with_playwright(req.url)
        page_text = page_text[:12_000]

    if len(page_text.strip()) < 100:
        raise HTTPException(422, "Page appears empty — even after JS render. Try a static careers page URL.")

    # ── 3. Claude extracts job listings ──────────────────────────────────────
    env_vars = dotenv_values()
    api_key = env_vars.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    claude = _anthropic.Anthropic(
        api_key=api_key,
        timeout=_anthropic.Timeout(60.0, connect=10.0),
    )

    extract_response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                f"Extract all job listings from this webpage.\n"
                f"Return a JSON array where each element has:\n"
                f"  title, company, location, description, url, job_type, remote (bool)\n"
                f"If a field is unknown use an empty string or false.\n"
                f"For url: use the job-specific apply link if visible; otherwise use: {req.url}\n"
                f"Return ONLY the raw JSON array — no markdown fences, no explanation.\n"
                f"If no jobs are found, return [].\n\n"
                f"PAGE URL: {req.url}\n\n"
                f"PAGE TEXT:\n{page_text}"
            ),
        }],
    )

    raw_text = extract_response.content[0].text.strip()
    # Strip accidental markdown fences
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    try:
        extracted_jobs = json_lib.loads(raw_text)
        if not isinstance(extracted_jobs, list):
            extracted_jobs = []
    except Exception as e:
        logger.error(f"Bulk apply JSON parse error: {e!r} | raw={raw_text[:300]}")
        raise HTTPException(422, f"Claude returned unparseable output — try a different URL")

    if not extracted_jobs:
        return {
            "imported": 0, "matched": 0, "emails_drafted": 0, "jobs": [],
            "message": "No job listings found on this page. Try a careers/jobs board URL.",
        }

    # ── 4. Deduplicate against existing DB ───────────────────────────────────
    existing_ids: set[str] = {
        row[0] for row in db.query(Job.external_id).all() if row[0]
    }

    new_jobs: list[dict] = []
    for j in extracted_jobs[:30]:
        job_url = str(j.get("url") or req.url)
        ext_id = hashlib.md5(
            f"bulk:{job_url}:{j.get('title', '')}".encode()
        ).hexdigest()
        if ext_id in existing_ids:
            continue
        new_jobs.append({
            "external_id": ext_id,
            "title":       str(j.get("title") or "Unknown Role"),
            "company":     str(j.get("company") or "Unknown Company"),
            "location":    str(j.get("location") or ""),
            "description": str(j.get("description") or ""),
            "url":         job_url,
            "source":      "bulk_import",
            "job_type":    str(j.get("job_type") or ""),
            "remote":      bool(j.get("remote", False)),
            "posted_at":   datetime.utcnow(),
            "is_referral_post": False,
        })

    if not new_jobs:
        return {
            "imported": 0, "matched": 0, "emails_drafted": 0, "jobs": [],
            "message": f"All {len(extracted_jobs)} jobs found are already in your database.",
        }

    if req.dry_run:
        return {
            "imported": len(new_jobs), "matched": 0, "emails_drafted": 0,
            "jobs": new_jobs,
            "message": f"Dry run — found {len(new_jobs)} new jobs (not saved)",
        }

    # ── 5. Score against resume ───────────────────────────────────────────────
    from agent.models.database import JobPreferences
    prefs = db.query(JobPreferences).first()
    prefs_dict = {
        "job_titles":       prefs.job_titles if prefs else [],
        "keywords":         prefs.keywords if prefs else [],
        "exclude_keywords": prefs.exclude_keywords if prefs else [],
        "locations":        prefs.locations if prefs else [],
        "remote_only":      prefs.remote_only if prefs else False,
        "experience_levels": prefs.experience_levels if prefs else [],
    }

    try:
        scores = await asyncio.wait_for(
            asyncio.to_thread(
                batch_match_jobs,
                jobs=new_jobs,
                resume_text=profile.resume_text,
                user_skills=profile.skills or [],
                user_preferences=prefs_dict,
                visa_status=profile.visa_status or "",
                work_rights=profile.work_rights or "",
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Bulk apply scoring timed out — using default 0.0 scores")
        scores = [
            {"score": 0.0, "recommendation": "skip", "reasons": ["timeout"],
             "skills_matched": [], "skills_missing": []}
            for _ in new_jobs
        ]

    # ── 6. Persist + draft emails ─────────────────────────────────────────────
    min_score = float(prefs.min_match_score) if prefs and prefs.min_match_score else 0.5
    matched_count = 0
    drafted_count = 0
    saved_jobs: list[dict] = []

    for job_data, match in zip(new_jobs, scores):
        score  = float(match.get("score", 0.0))
        status = (
            ApplicationStatus.matched
            if score >= min_score
            else ApplicationStatus.skipped
        )
        job_data["match_score"]    = score
        job_data["match_reasons"]  = match.get("reasons", [])
        job_data["skills_matched"] = match.get("skills_matched", [])
        job_data["skills_missing"] = match.get("skills_missing", [])

        try:
            job_obj = Job(
                **{k: v for k, v in job_data.items() if hasattr(Job, k)},
                status=status,
            )
            db.add(job_obj)
            db.commit()
            db.refresh(job_obj)
        except Exception as e:
            logger.error(f"Bulk apply DB error: {e}")
            db.rollback()
            continue

        saved_jobs.append(_job_dict(job_obj))

        if status == ApplicationStatus.matched:
            matched_count += 1
            try:
                profile_dict = {
                    "name":          profile.name,
                    "email":         profile.email,
                    "phone":         profile.phone,
                    "linkedin_url":  profile.linkedin_url,
                    "github_url":    profile.github_url,
                    "portfolio_url": profile.portfolio_url,
                }
                email_data = await asyncio.wait_for(
                    asyncio.to_thread(
                        draft_application_email,
                        job=job_data,
                        resume_text=profile.resume_text,
                        user_profile=profile_dict,
                        email_type="application",
                    ),
                    timeout=90.0,
                )
                # to_address is NOT NULL — fall back to "careers@{domain}" when unknown
                to_addr = email_data.get("suggested_to_address") or ""
                if not to_addr:
                    import re as _re
                    domain_m = _re.search(r"https?://(?:www\.)?([^/]+)", str(job_data.get("url", "")))
                    to_addr = f"careers@{domain_m.group(1)}" if domain_m else "careers@company.com"
                email_obj = Email(
                    job_id=job_obj.id,
                    email_type="application",
                    to_address=to_addr,
                    to_name=email_data.get("suggested_to_name", "Hiring Manager"),
                    subject=email_data.get("subject", ""),
                    body=email_data.get("body", ""),
                    status="draft",
                )
                db.add(email_obj)
                db.commit()
                drafted_count += 1
            except Exception as e:
                logger.error(f"Bulk apply email draft error: {e}")

    return {
        "imported":       len(new_jobs),
        "matched":        matched_count,
        "emails_drafted": drafted_count,
        "jobs":           saved_jobs,
        "message": (
            f"Imported {len(new_jobs)} jobs · "
            f"{matched_count} matched · "
            f"{drafted_count} emails drafted"
        ),
    }


# ── Auto-apply via Playwright ─────────────────────────────────────────────────

class AutoApplyRequest(BaseModel):
    job_id: int
    portal: str = "auto"  # "linkedin" | "seek" | "indeed" | "greenhouse" | "auto"


@router.post("/auto-apply/{job_id}")
async def auto_apply_job(job_id: int, db: Session = Depends(get_db)):
    """
    Attempt automatic form submission for a job via Playwright.
    Returns a screenshot of the result and the outcome status.
    """
    from agent.auto_apply.playwright_apply import auto_apply_to_job

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.url:
        raise HTTPException(400, "Job has no application URL")

    profile = db.query(UserProfile).first()
    if not profile:
        raise HTTPException(400, "No profile found — set up your profile in Settings")

    result = await auto_apply_to_job(job=_job_dict(job), profile=profile)

    if result.get("success"):
        job.status = ApplicationStatus.applied
        db.commit()

    return result


# ── Wildcard /{job_id} routes LAST ───────────────────────────────────────────

@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.patch("/{job_id}/status")
def update_job_status(job_id: int, status: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = status
    db.commit()
    return {"ok": True, "status": status}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_dict(job: Job) -> dict:
    return {
        "id":             job.id,
        "external_id":    job.external_id,
        "title":          job.title,
        "company":        job.company,
        "location":       job.location,
        "description":    job.description,
        "url":            job.url,
        "source":         job.source,
        "salary_min":     job.salary_min,
        "salary_max":     job.salary_max,
        "salary_currency": job.salary_currency,
        "job_type":       job.job_type,
        "remote":         job.remote,
        "match_score":    job.match_score,
        "match_reasons":  job.match_reasons,
        "skills_matched": job.skills_matched,
        "skills_missing": job.skills_missing,
        "posted_at":      job.posted_at.isoformat() if job.posted_at else None,
        "found_at":       job.found_at.isoformat() if job.found_at else None,
        "status":         job.status,
        "is_referral_post": job.is_referral_post,
        "url_valid":        job.url_valid,
    }
