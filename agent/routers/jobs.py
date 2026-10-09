import asyncio
import hashlib
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, or_
from sqlalchemy.orm import Session

from agent.models.database import get_db, Job, Email, UserProfile, ApplicationStatus, SearchRun
from agent.scheduler import run_search_cycle, is_search_running
from agent.utils import is_public_url, safe_http_url, spawn, utcnow, UNTRUSTED_NOTE, parse_llm_json

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
    search: Optional[str] = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=500),
    include_hidden: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    elif not include_hidden:
        # Hide what quality control / scoring set aside; pick the status in the filter to see them
        q = q.filter(Job.status.notin_([ApplicationStatus.skipped, ApplicationStatus.expired]))
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
    if is_search_running():
        return {"ok": True, "status": "already_running"}
    spawn(run_search_cycle())   # opens and closes its own session
    return {"ok": True, "status": "search started"}


@router.get("/search/status")
def search_status(db: Session = Depends(get_db)):
    """Check if a search is running + current run progress (polled by the dashboard)."""
    latest = db.query(SearchRun.started_at, SearchRun.jobs_found).order_by(SearchRun.id.desc()).first()
    scored = matched = 0
    if latest:
        scored, matched = db.query(
            func.count(Job.id),
            func.coalesce(func.sum(case((Job.match_score >= 0.5, 1), else_=0)), 0),
        ).filter(Job.found_at >= latest.started_at).one()
    return {
        "is_running": is_search_running(),
        "jobs_found": (latest.jobs_found or 0) if latest else 0,
        "jobs_scored": scored or 0,
        "jobs_matched": matched or 0,
    }


@router.get("/stats/summary")
def job_stats(db: Session = Depends(get_db)):
    total = db.query(Job).count()
    matched = db.query(Job).filter(Job.match_score >= 0.7).count()
    applied = db.query(Job).filter(Job.status == ApplicationStatus.email_sent).count()
    by_source = db.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
    by_status = db.query(Job.status, func.count(Job.id)).group_by(Job.status).all()
    return {
        "total_found": total,
        "total_matched": matched,
        "total_applied": applied,
        "by_source": {src: n for src, n in by_source},
        "by_status": {(st.value if hasattr(st, "value") else st): n for st, n in by_status},
    }


# ── Link verification ─────────────────────────────────────────────────────────

@router.post("/verify-links")
async def verify_links():
    """HEAD-checks job URLs that haven't been verified yet and marks url_valid."""
    from agent.tools.link_checker import verify_unchecked_links
    return await verify_unchecked_links(limit=200)


# ── Quality control ──────────────────────────────────────────────────────────

@router.get("/qc/status")
def qc_status():
    """Result of the last automatic quality-control pass."""
    from agent.quality_control import last_result
    return last_result()


@router.post("/qc/run")
async def qc_run():
    """Run quality control now (it also runs automatically after every search)."""
    from agent.quality_control import last_result, run_quality_control
    if last_result()["running"]:
        return {"started": False, "detail": "Quality control is already running"}
    spawn(run_quality_control())
    return {"started": True}


# ── Bulk import from URL ──────────────────────────────────────────────────────

class BulkApplyRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    dry_run: bool = False


@router.post("/bulk-apply")
async def bulk_apply_from_url(req: BulkApplyRequest, db: Session = Depends(get_db)):
    """
    Fetch a webpage of job listings, extract them via Claude, score them
    against the user's resume, persist to DB, and draft application emails.
    """
    from agent.ai.claude_agent import batch_match_jobs, draft_application_email, client, MODEL

    profile = db.query(UserProfile).first()
    if not profile or not profile.resume_text:
        raise HTTPException(400, "Upload your resume first in Settings → Profile")
    # SSRF guard: only public http(s) pages, never localhost / LAN / metadata addresses
    if not await is_public_url(req.url):
        raise HTTPException(400, "Enter a public http(s) careers page URL")

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
        ) as http:
            resp = await http.get(req.url)
            resp.raise_for_status()
            # A public page can still redirect to an internal address
            if not await is_public_url(str(resp.url)):
                raise HTTPException(400, "That page redirects to a non-public address")
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
            tag.decompose()
        page_text = soup.get_text(separator="\n", strip=True)[:12_000]
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(400, f"Page returned HTTP {e.response.status_code}: {req.url}") from e
    except Exception as e:
        raise HTTPException(400, f"Could not fetch URL: {e}") from e

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

    # ── 3. Claude extracts job listings (in a thread: the SDK call is blocking) ─
    prompt = (
        f"Extract all job listings from this webpage.\n"
        f"Return a JSON array where each element has:\n"
        f"  title, company, location, description, url, job_type, remote (bool)\n"
        f"If a field is unknown use an empty string or false.\n"
        f"For url: use the job-specific apply link if visible; otherwise use: {req.url}\n"
        f"Return ONLY the raw JSON array - no markdown fences, no explanation.\n"
        f"If no jobs are found, return [].\n{UNTRUSTED_NOTE}\n\n"
        f"PAGE URL: {req.url}\n\n"
        f"PAGE TEXT:\n{page_text}"
    )
    try:
        extract_response = await asyncio.wait_for(asyncio.to_thread(
            client.messages.create, model=MODEL, max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        ), timeout=90)
        extracted_jobs = parse_llm_json(extract_response.content[0].text)
        if not isinstance(extracted_jobs, list):
            extracted_jobs = []
    except Exception as e:
        logger.error(f"Bulk apply extraction failed: {e!r}")
        raise HTTPException(422, "Couldn't read job listings from that page - try a different URL") from e

    if not extracted_jobs:
        return {
            "imported": 0, "matched": 0, "emails_drafted": 0, "jobs": [],
            "message": "No job listings found on this page. Try a careers/jobs board URL.",
        }

    # ── 4. Deduplicate against existing DB (only look up the ids we have) ────
    candidates: dict[str, dict] = {}
    for j in extracted_jobs[:30]:
        if not isinstance(j, dict):
            continue
        job_url = safe_http_url(j.get("url")) or req.url
        ext_id = hashlib.md5(f"bulk:{job_url}:{j.get('title', '')}".encode(), usedforsecurity=False).hexdigest()
        candidates[ext_id] = {
            "external_id": ext_id,
            "title":       str(j.get("title") or "Unknown Role")[:300],
            "company":     str(j.get("company") or "Unknown Company")[:200],
            "location":    str(j.get("location") or "")[:200],
            "description": str(j.get("description") or "")[:4000],
            "url":         job_url,
            "source":      "bulk_import",
            "job_type":    str(j.get("job_type") or "")[:50],
            "remote":      bool(j.get("remote", False)),
            "posted_at":   utcnow(),
            "is_referral_post": False,
        }
    existing = {eid for (eid,) in db.query(Job.external_id).filter(Job.external_id.in_(list(candidates)))}
    new_jobs = [v for k, v in candidates.items() if k not in existing]

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

    for job_data, match in zip(new_jobs, scores, strict=False):
        try:
            score = float(match.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
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
                # Leave the address empty rather than guessing one - you fill it in before sending
                email_obj = Email(
                    job_id=job_obj.id,
                    email_type="application",
                    to_address=email_data.get("suggested_to_address") or None,
                    to_name=email_data.get("suggested_to_name", "Hiring Manager"),
                    subject=email_data.get("subject", ""),
                    body=email_data.get("body", ""),
                    status="draft",
                )
                db.add(email_obj)
                db.commit()
                drafted_count += 1
            except Exception as e:
                db.rollback()
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
    try:
        new_status = ApplicationStatus(status)
    except ValueError as e:
        raise HTTPException(400, f"Unknown status '{status}'") from e
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = new_status
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
        "url":            safe_http_url(job.url),
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
        "status":         job.status.value if hasattr(job.status, "value") else job.status,
        "is_referral_post": job.is_referral_post,
        "url_valid":        job.url_valid,
        "qc_reason":        job.qc_reason,
    }
