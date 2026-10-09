"""
Job search orchestrator + APScheduler for automated runs.
Ties together scraping → AI batch-matching → email drafting → auto-send.
"""
import asyncio
import logging
import re
from datetime import timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.models.database import (
    SessionLocal, Job, Application, Email, UserProfile,
    JobPreferences, SearchRun, ApplicationStatus,
)
from agent.scrapers.job_scraper import run_all_scrapers
from agent.ai.claude_agent import (
    batch_match_jobs, draft_application_email, find_company_email,
)
from agent.gmail_service.gmail_service import send_email, create_draft, gmail_ready
from agent.utils import safe_http_url, spawn, utcnow

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

# Global lock — prevents two concurrent search cycles
_search_lock = asyncio.Lock()

# Tunables
BATCH_SIZE     = 10       # jobs per Claude scoring call
CONCURRENCY    = 2        # parallel Claude calls (stay under rate limit)
MAX_DURATION_S = 45 * 60  # 45-minute hard stop per cycle (includes email drafting)


def is_search_running() -> bool:
    return _search_lock.locked()


async def _score_batch(batch: list[dict], resume_text: str,
                       skills: list, prefs: dict,
                       visa_status: str = "", work_rights: str = "") -> list[dict]:
    """Score a batch with a hard 120s timeout to prevent hanging Claude calls."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                batch_match_jobs,
                jobs=batch,
                resume_text=resume_text,
                user_skills=skills,
                user_preferences=prefs,
                visa_status=visa_status,
                work_rights=work_rights,
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.error("Batch scoring timed out after 120s — returning empty scores")
        return [{"score": 0.0, "recommendation": "skip", "reasons": ["timeout"],
                 "skills_matched": [], "skills_missing": []} for _ in batch]


async def run_search_cycle(db: Optional[Session] = None) -> dict:
    """
    Full search cycle:
    1. Scrape job sources
    2. Deduplicate (only unseen external_ids)
    3. Batch-score with Claude (BATCH_SIZE jobs/call, CONCURRENCY parallel)
       — commits each batch immediately for live progress
    4. Draft + optionally auto-send emails for matched jobs
    5. Quality control (dead links, closed/old ads, criteria) + referral discovery
    """
    if _search_lock.locked():
        logger.warning("Search cycle already running — skipping")
        return {"error": "Search already running"}

    async with _search_lock:
        close_db = db is None
        if db is None:
            db = SessionLocal()

        cycle_start = utcnow()
        run = SearchRun(started_at=cycle_start, status="running")
        db.add(run)
        db.commit()
        run_id = run.id

        try:
            prefs   = db.query(JobPreferences).first()
            profile = db.query(UserProfile).first()

            if not prefs or not profile or not profile.resume_text:
                logger.warning("No preferences or resume — skipping")
                run.status = "failed"
                run.error_message = "No preferences or resume configured"
                db.commit()
                return {"error": "No preferences or resume configured"}

            sources = prefs.sources or ["linkedin", "indeed", "glassdoor", "seek"]
            run.sources_searched = sources

            # ── 1. Scrape ────────────────────────────────────────────────────
            logger.info(f"Scraping: {prefs.job_titles} in {prefs.locations}")
            raw_jobs = await run_all_scrapers(
                titles=prefs.job_titles or [],
                locations=prefs.locations or [],
                keywords=prefs.keywords or [],
                sources=sources,
                hours_old=(prefs.search_frequency_hours or 6) * 2,
            )
            run.jobs_found = len(raw_jobs)
            db.commit()

            # ── 1b. Location filter — drop jobs from wrong regions ───────────
            preferred_locs = [l.lower() for l in (prefs.locations or [])]
            wants_australia = any(
                k in loc for loc in preferred_locs
                for k in ("australia", "melbourne", "sydney", "brisbane", "perth", "adelaide", "hobart", "canberra")
            )
            wants_us = any(
                k in loc for loc in preferred_locs
                for k in ("usa", "us", "united states", "new york", "san francisco", "los angeles",
                          "chicago", "denver", "seattle", "boston")
            )
            wants_remote = any("remote" in loc for loc in preferred_locs)

            AU_KEYWORDS = {"australia", "melbourne", "sydney", "brisbane", "perth",
                           "adelaide", "hobart", "canberra", "au", "vic", "nsw", "qld"}
            US_KEYWORDS = {"united states", "usa", "new york", "san francisco", "los angeles",
                           "chicago", "denver", "seattle", "boston", "remote (us)", "us only"}

            def _location_ok(job: dict) -> bool:
                """Return True if this job's location matches user's preferred regions."""
                job_loc = (job.get("location") or "").lower()
                job_source = (job.get("source") or "").lower()

                # top_companies entries are pre-filtered for AU — always include
                if job_source == "top_companies":
                    return True
                # remote / no location — include if user wants remote or AU
                if not job_loc or job_loc in ("remote", "various", ""):
                    return wants_remote or wants_australia
                # Check AU match
                if wants_australia and not wants_us:
                    # Include if AU keyword found; exclude if US-only keyword found
                    has_au = any(k in job_loc for k in AU_KEYWORDS)
                    has_us_only = any(k in job_loc for k in US_KEYWORDS) and not has_au
                    return has_au or (not has_us_only and wants_remote)
                # Both regions wanted — let everything through
                return True

            if preferred_locs and (wants_australia and not wants_us):
                before = len(raw_jobs)
                raw_jobs = [j for j in raw_jobs if _location_ok(j)]
                logger.info(f"Location filter: {before} → {len(raw_jobs)} jobs "
                            f"(dropped {before - len(raw_jobs)} non-AU jobs)")
            run.jobs_found = len(raw_jobs)
            db.commit()

            # ── 2. Deduplicate ───────────────────────────────────────────────
            # Drop unsafe links (javascript:, internal addresses...) from scraped data
            raw_jobs = [j for j in raw_jobs if safe_http_url(j.get("url"))]
            candidate_ids = [j["external_id"] for j in raw_jobs if j.get("external_id")]
            existing_ids: set[str] = set()
            for i in range(0, len(candidate_ids), 500):   # stay under SQLite's variable limit
                existing_ids.update(eid for (eid,) in db.query(Job.external_id)
                                    .filter(Job.external_id.in_(candidate_ids[i:i + 500])))
            new_jobs = [j for j in raw_jobs if j.get("external_id") not in existing_ids]

            # Excluded keywords in the title: skip before paying for Claude scoring
            excluded = [k.strip().lower() for k in (prefs.exclude_keywords or []) if k and k.strip()]
            if excluded:
                pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in excluded) + r")\b", re.I)
                before = len(new_jobs)
                new_jobs = [j for j in new_jobs if not pattern.search(j.get("title") or "")]
                if before != len(new_jobs):
                    logger.info(f"Excluded-keyword pre-filter: skipped {before - len(new_jobs)} jobs")
            logger.info(f"Scraped {len(raw_jobs)} | new: {len(new_jobs)}")

            if not new_jobs:
                logger.info("No new jobs — cycle complete")
                run.jobs_matched = run.emails_drafted = run.emails_sent = 0
                run.status = "completed"
                run.completed_at = utcnow()
                db.commit()
                return {"jobs_found": len(raw_jobs), "jobs_matched": 0,
                        "emails_drafted": 0, "emails_sent": 0, "run_id": run_id}

            prefs_dict = {
                "job_titles": prefs.job_titles, "keywords": prefs.keywords,
                "exclude_keywords": prefs.exclude_keywords, "locations": prefs.locations,
                "remote_only": prefs.remote_only, "min_salary": prefs.min_salary,
                "job_types": prefs.job_types, "experience_levels": prefs.experience_levels,
            }

            # ── 3. Score + commit in interleaved rounds ──────────────────────
            batches = [new_jobs[i:i+BATCH_SIZE] for i in range(0, len(new_jobs), BATCH_SIZE)]
            logger.info(f"Scoring {len(new_jobs)} jobs | {len(batches)} batches "
                        f"| {BATCH_SIZE}/batch | {CONCURRENCY} parallel")

            matched_count  = 0
            drafted_count  = 0
            sent_count     = 0
            applications_today = db.query(Application).filter(
                Application.created_at >= utcnow() - timedelta(days=1)
            ).count()

            for chunk_start in range(0, len(batches), CONCURRENCY):
                # Hard timeout
                if (utcnow() - cycle_start).total_seconds() > MAX_DURATION_S:
                    logger.warning(f"{MAX_DURATION_S // 60}-min timeout reached — stopping early")
                    break

                chunk = batches[chunk_start:chunk_start + CONCURRENCY]

                # Score this chunk in parallel
                results = await asyncio.gather(
                    *[_score_batch(b, profile.resume_text, profile.skills or [], prefs_dict,
                                  profile.visa_status or "", profile.work_rights or "")
                      for b in chunk],
                    return_exceptions=True,
                )

                # Commit this chunk immediately (live progress in DB)
                for batch, batch_scores in zip(chunk, results, strict=True):
                    if isinstance(batch_scores, Exception):
                        logger.error(f"Batch error: {batch_scores}")
                        batch_scores = [{"score": 0.0, "recommendation": "skip",
                                         "reasons": [], "skills_matched": [], "skills_missing": []}
                                        for _ in batch]

                    for job_data, match in zip(batch, batch_scores, strict=False):
                        await asyncio.sleep(0)
                        try:
                            try:
                                score = float(match.get("score", 0.0))
                            except (TypeError, ValueError):
                                score = 0.0
                            status = (ApplicationStatus.skipped
                                      if score < (prefs.min_match_score or 0.5)
                                      else ApplicationStatus.matched)

                            job_data["match_score"]    = score
                            job_data["match_reasons"]  = match.get("reasons", [])
                            job_data["skills_matched"] = match.get("skills_matched", [])
                            job_data["skills_missing"] = match.get("skills_missing", [])

                            job_obj = Job(
                                **{k: v for k, v in job_data.items() if hasattr(Job, k)},
                                status=status,
                            )
                            db.add(job_obj)
                            try:
                                db.flush()
                            except IntegrityError:
                                db.rollback()
                                continue

                            if status == ApplicationStatus.skipped:
                                db.commit()
                                continue

                            matched_count += 1
                            # ── Commit job first so it's always persisted ──
                            db.commit()

                            # ── Draft email (separate transaction) ──────────
                            try:
                                profile_dict = {
                                    "name": profile.name, "email": profile.email,
                                    "phone": profile.phone, "linkedin_url": profile.linkedin_url,
                                    "github_url": profile.github_url, "portfolio_url": profile.portfolio_url,
                                }
                                email_data = await asyncio.wait_for(
                                    asyncio.to_thread(
                                        draft_application_email,
                                        job=job_data, resume_text=profile.resume_text,
                                        user_profile=profile_dict, email_type="application",
                                    ),
                                    timeout=90.0,
                                )
                                to_address = email_data.get("suggested_to_address") or ""
                                address_guessed = not to_address
                                if not to_address:
                                    contact = await asyncio.wait_for(
                                        asyncio.to_thread(
                                            find_company_email,
                                            job_data.get("company", ""), job_data.get("title", "")
                                        ),
                                        timeout=30.0,
                                    )
                                    to_address = contact.get("likely_email", "")

                                email_obj = Email(
                                    job_id=job_obj.id, email_type="application",
                                    to_address=to_address or None,
                                    to_name=email_data.get("suggested_to_name", "Hiring Manager"),
                                    subject=email_data.get("subject", ""),
                                    body=email_data.get("body", ""),
                                    status="draft",
                                )
                                db.add(email_obj)
                                drafted_count += 1

                                # Auto-send
                                # Never auto-send to an address the model guessed; those stay drafts
                                if (score >= (prefs.auto_send_above_score or 0.85)
                                        and to_address and not address_guessed
                                        and applications_today < (prefs.max_applications_per_day or 10)):
                                    try:
                                        result = await asyncio.to_thread(
                                            send_email,
                                            to_address=to_address, subject=email_obj.subject,
                                            body=email_obj.body, to_name=email_obj.to_name,
                                            from_name=profile.name,
                                        )
                                        email_obj.status = "sent"
                                        email_obj.sent_at = utcnow()
                                        email_obj.gmail_message_id = result.get("message_id")
                                        email_obj.gmail_thread_id  = result.get("thread_id")
                                        job_obj.status = ApplicationStatus.email_sent
                                        db.add(Application(
                                            job_id=job_obj.id, status=ApplicationStatus.email_sent,
                                            cover_letter=email_obj.body, applied_at=utcnow(),
                                            follow_up_at=utcnow() + timedelta(days=7),
                                        ))
                                        sent_count += 1
                                        applications_today += 1
                                        logger.info(f"Auto-sent → {to_address} ({job_obj.title})")
                                    except Exception as e:
                                        logger.error(f"Email send failed: {e}")
                                        email_obj.error_message = str(e)
                                elif to_address and gmail_ready():
                                    # Also put it in your Gmail Drafts folder, ready to review there
                                    try:
                                        await asyncio.to_thread(
                                            create_draft,
                                            to_address=to_address, subject=email_obj.subject,
                                            body=email_obj.body, to_name=email_obj.to_name,
                                            from_name=profile.name,
                                        )
                                    except Exception as e:
                                        logger.warning(f"Gmail draft creation failed: {e}")

                                if email_obj.status != "sent":
                                    job_obj.status = ApplicationStatus.draft_ready
                                db.commit()
                            except asyncio.TimeoutError:
                                logger.warning(f"Email draft timed out for '{job_obj.title}' — job saved without email")
                                db.rollback()
                            except Exception as e:
                                logger.warning(f"Email draft failed for '{job_obj.title}': {e} — job saved without email")
                                db.rollback()

                        except Exception as e:
                            logger.error(f"Job commit error '{job_data.get('title')}': {e}")
                            try:
                                db.rollback()
                            except Exception:
                                pass

            # ── 4. Finalise ──────────────────────────────────────────────────
            try:
                run = db.query(SearchRun).filter(SearchRun.id == run_id).first()
                if run:
                    run.jobs_matched   = matched_count
                    run.emails_drafted = drafted_count
                    run.emails_sent    = sent_count
                    run.status         = "completed"
                    run.completed_at   = utcnow()
                    db.commit()
            except Exception as e:
                logger.error(f"Failed to finalise run: {e}")
                db.rollback()

            elapsed = (utcnow() - cycle_start).total_seconds()
            stats = {
                "jobs_found": len(raw_jobs), "new_jobs": len(new_jobs),
                "jobs_matched": matched_count, "emails_drafted": drafted_count,
                "emails_sent": sent_count, "run_id": run_id,
                "duration_s": round(elapsed),
            }
            logger.info(f"Search cycle complete in {elapsed:.0f}s: {stats}")

            # ── 5. Quality control, then referral discovery (background, automatic) ─
            spawn(_post_search_pipeline())

            return stats

        except Exception as e:
            logger.exception(f"Search cycle failed: {e}")
            try:
                db.rollback()
                run = db.query(SearchRun).filter(SearchRun.id == run_id).first()
                if run:
                    run.status = "failed"
                    run.error_message = str(e)
                    db.commit()
            except Exception as inner:
                logger.error(f"Could not record failed run: {inner}")
            return {"error": str(e)}
        finally:
            if close_db:
                db.close()


async def _post_search_pipeline():
    """Runs after every search: quality control first, so referral discovery sees clean data."""
    from agent.quality_control import run_quality_control
    await run_quality_control()
    await _auto_referral_discovery()


async def _auto_referral_discovery():
    try:
        from agent.models.database import ReferralProfile
        db = SessionLocal()
        try:
            rp = db.query(ReferralProfile).first()
            enabled = bool(rp and rp.auto_discover)
        finally:
            db.close()
        if enabled:
            from agent.referrals.agent import discover_threads
            result = await discover_threads()
            logger.info(f"Referral discovery: {result}")
    except Exception as e:
        logger.warning(f"Referral discovery failed: {e}")


async def _scheduled_search():
    """Wrapper for scheduled runs — skips if already running."""
    if _search_lock.locked():
        logger.info("Scheduled search skipped — previous cycle still running")
        return
    await run_search_cycle()


def start_scheduler(search_frequency_hours: int = 6):
    if not scheduler.running:
        scheduler.add_job(
            _scheduled_search,
            trigger=IntervalTrigger(hours=search_frequency_hours),
            id="job_search",
            replace_existing=True,
        )
        # QC also runs on its own timer, so stale ads get cleaned up even between searches
        scheduler.add_job(
            _scheduled_qc,
            trigger=IntervalTrigger(hours=12),
            id="quality_control",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(f"Scheduler started — every {search_frequency_hours}h")


async def _scheduled_qc():
    if _search_lock.locked():
        return          # the running search will trigger QC when it finishes
    from agent.quality_control import run_quality_control
    await run_quality_control()


def reschedule(search_frequency_hours: Optional[int]) -> None:
    """Apply a new search interval without restarting the backend."""
    hours = max(1, int(search_frequency_hours or 6))
    if scheduler.running and scheduler.get_job("job_search"):
        scheduler.reschedule_job("job_search", trigger=IntervalTrigger(hours=hours))
        logger.info(f"Search interval changed to every {hours}h")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
