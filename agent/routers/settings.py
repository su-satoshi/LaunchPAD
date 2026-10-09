import asyncio
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.utils import utcnow

from agent.ai.claude_agent import analyze_resume
from agent.models.database import JobPreferences, UserProfile, get_db
from agent.scrapers.job_scraper import _normalize_location

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

MAX_RESUME_BYTES = 10 * 1024 * 1024


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    skills: Optional[list[str]] = None
    years_experience: Optional[int] = Field(None, ge=0, le=60)
    visa_status: Optional[str] = None
    work_rights: Optional[str] = None


class PreferencesUpdate(BaseModel):
    job_titles: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    exclude_keywords: Optional[list[str]] = None
    locations: Optional[list[str]] = None
    remote_only: Optional[bool] = None
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    job_types: Optional[list[str]] = None
    experience_levels: Optional[list[str]] = None
    sources: Optional[list[str]] = None
    min_match_score: Optional[float] = Field(None, ge=0, le=1)
    auto_send_above_score: Optional[float] = Field(None, ge=0, le=1)
    max_applications_per_day: Optional[int] = Field(None, ge=0, le=100)
    search_frequency_hours: Optional[int] = Field(None, ge=1, le=168)
    active: Optional[bool] = None


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    if not profile:
        return {}
    return _profile_dict(profile)


@router.put("/profile")
def update_profile(data: ProfileUpdate, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(profile, field, val)
    profile.updated_at = utcnow()
    db.commit()
    return _profile_dict(profile)


@router.post("/resume")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a resume (PDF or TXT). Claude will parse it automatically."""
    content = await file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume is larger than 10 MB")
    filename = (file.filename or "").lower()
    if not filename.endswith((".pdf", ".txt", ".md")):
        raise HTTPException(400, "Upload a PDF or TXT resume")
    text = ""

    if filename.endswith(".pdf"):
        try:
            import pdfplumber
            def _pdf_text() -> str:
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    return "\n".join(page.extract_text() or "" for page in pdf.pages[:20])
            text = await asyncio.to_thread(_pdf_text)
        except ImportError:
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError as e:
                raise HTTPException(400, "Install pdfplumber or pypdf to parse PDFs: pip install pdfplumber") from e
        except Exception as e:
            raise HTTPException(400, "Couldn't read that PDF") from e
    else:
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(400, "Could not extract text from file")

    # AI parse (blocking SDK call - keep the server responsive)
    parsed = await asyncio.to_thread(analyze_resume, text[:60_000])

    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)

    profile.resume_text = text
    profile.resume_filename = file.filename
    if parsed.get("name") and not profile.name:
        profile.name = parsed["name"]
    if parsed.get("email") and not profile.email:
        profile.email = parsed["email"]
    if parsed.get("phone") and not profile.phone:
        profile.phone = parsed["phone"]
    if parsed.get("location") and not profile.location:
        profile.location = parsed["location"]
    if parsed.get("skills"):
        profile.skills = parsed["skills"]
    if parsed.get("years_experience"):
        profile.years_experience = parsed["years_experience"]
    if parsed.get("education"):
        profile.education = parsed["education"]
    if parsed.get("work_history"):
        profile.work_history = parsed["work_history"]
    profile.updated_at = utcnow()
    db.commit()

    return {"ok": True, "parsed": parsed, "filename": file.filename}


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db)):
    prefs = db.query(JobPreferences).first()
    if not prefs:
        return {}
    return _prefs_dict(prefs)


@router.put("/preferences")
def update_preferences(data: PreferencesUpdate, db: Session = Depends(get_db)):
    prefs = db.query(JobPreferences).first()
    if not prefs:
        prefs = JobPreferences()
        db.add(prefs)

    update_data = data.model_dump(exclude_none=True)

    # Normalize locations if provided
    if "locations" in update_data and update_data["locations"]:
        normalized_locations = []
        for location in update_data["locations"]:
            normalized, _ = _normalize_location(location)
            normalized_locations.append(normalized)
        update_data["locations"] = normalized_locations
        logger.info(f"Normalized locations: {update_data['locations']}")

    for field, val in update_data.items():
        setattr(prefs, field, val)
    prefs.updated_at = utcnow()
    db.commit()
    if "search_frequency_hours" in update_data:
        # Apply the new interval now instead of after the next restart
        from agent.scheduler import reschedule
        reschedule(prefs.search_frequency_hours)
    return _prefs_dict(prefs)


def _profile_dict(p: UserProfile) -> dict:
    return {
        "name": p.name, "email": p.email, "phone": p.phone,
        "location": p.location, "linkedin_url": p.linkedin_url,
        "github_url": p.github_url, "portfolio_url": p.portfolio_url,
        "skills": p.skills or [], "years_experience": p.years_experience,
        "education": p.education or [], "work_history": p.work_history or [],
        "resume_filename": p.resume_filename,
        "has_resume": bool(p.resume_text),
        "visa_status": p.visa_status or "",
        "work_rights": p.work_rights or "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _prefs_dict(p: JobPreferences) -> dict:
    return {
        "job_titles": p.job_titles or [],
        "keywords": p.keywords or [],
        "exclude_keywords": p.exclude_keywords or [],
        "locations": p.locations or [],
        "remote_only": p.remote_only,
        "min_salary": p.min_salary,
        "max_salary": p.max_salary,
        "job_types": p.job_types or [],
        "experience_levels": p.experience_levels or [],
        "sources": p.sources or [],
        "min_match_score": p.min_match_score,
        "auto_send_above_score": p.auto_send_above_score,
        "max_applications_per_day": p.max_applications_per_day,
        "search_frequency_hours": p.search_frequency_hours,
        "active": p.active,
    }


@router.get("/api-status")
async def get_api_status(db: Session = Depends(get_db)):
    """Return status and estimated usage for all connected APIs."""
    import os
    from pathlib import Path
    from agent.models.database import Job, Email
    from agent.tools import firecrawl_client, browser_agent

    # Claude API
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    claude_ok = bool(api_key and len(api_key) > 20)

    # Gmail
    token_path   = Path(os.getenv("GMAIL_TOKEN_PATH",       "./gmail_token.json"))
    creds_path   = Path(os.getenv("GMAIL_CREDENTIALS_PATH", "./gmail_credentials.json"))
    gmail_from   = os.getenv("GMAIL_FROM_ADDRESS", "")
    # Detect placeholder value
    if gmail_from in ("you@gmail.com", "", "your@email.com"):
        gmail_status = "not_configured"
    elif token_path.exists():
        gmail_status = "connected"
    elif creds_path.exists():
        gmail_status = "needs_auth"
    else:
        gmail_status = "not_configured"

    # Totals
    total_jobs   = db.query(Job).count()
    total_emails = db.query(Email).count()
    sent_emails  = db.query(Email).filter(Email.status == "sent").count()

    # Rough token estimates (conservative)
    # ~1 200 tokens / job match, ~900 tokens / email draft
    est_tokens = total_jobs * 1_200 + total_emails * 900
    # claude-sonnet-4-6: $3/M input, $15/M output  (assume 65% in, 35% out)
    est_cost = (est_tokens * 0.65 / 1_000_000) * 3 + (est_tokens * 0.35 / 1_000_000) * 15

    # Per-action cost breakdown
    cost_breakdown = {
        "job_scoring":    {"count": total_jobs, "tokens_each": 1200,
                           "cost_usd": round(total_jobs * 1200 * 0.65 / 1e6 * 3 + total_jobs * 1200 * 0.35 / 1e6 * 15, 4)},
        "email_drafting": {"count": total_emails, "tokens_each": 900,
                           "cost_usd": round(total_emails * 900 * 0.65 / 1e6 * 3 + total_emails * 900 * 0.35 / 1e6 * 15, 4)},
    }

    return {
        "claude": {
            "status":         "connected" if claude_ok else "not_configured",
            "model":          "claude-sonnet-4-6",
            "est_tokens":     est_tokens,
            "est_cost_usd":   round(est_cost, 4),
            "cost_breakdown": cost_breakdown,
        },
        "gmail": {
            "status":         gmail_status,
            "from_address":   gmail_from,
            "emails_sent":    sent_emails,
            "emails_drafted": total_emails,
        },
        "database": {
            "total_jobs":   total_jobs,
            "total_emails": total_emails,
        },
        "firecrawl": {
            "status": "connected" if await firecrawl_client.is_available(force=True) else "not_running",
            "url":    firecrawl_client.FIRECRAWL_URL,
            "self_hosted": True,
        },
        "browser_agent": await browser_agent.status(),
    }


@router.get("/gmail/authorize-url")
def gmail_authorize_url():
    """Return the Google sign-in URL; the token is saved when you finish signing in."""
    from agent.gmail_service.gmail_service import start_oauth
    try:
        return {"auth_url": start_oauth(), "message": "Sign in with Google in the new tab"}
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:
        logger.error(f"Gmail OAuth setup failed: {e}")
        raise HTTPException(500, "Couldn't start Gmail sign-in - check gmail_credentials.json") from e
