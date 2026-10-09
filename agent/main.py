import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.models.database import init_db
from agent.routers import jobs, emails, settings, applications, referrals
from agent.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised")
    # SQLite column migration — safe to run on every startup
    from agent.models.database import SessionLocal
    from sqlalchemy import text as _text
    _db = SessionLocal()
    try:
        _db.execute(_text("ALTER TABLE jobs ADD COLUMN url_valid BOOLEAN"))
        _db.commit()
    except Exception:
        _db.rollback()  # Column already exists — ignore
    finally:
        _db.close()
    from agent.models.database import SessionLocal, JobPreferences
    db = SessionLocal()
    prefs = db.query(JobPreferences).first()
    frequency = prefs.search_frequency_hours if prefs else 6
    db.close()
    start_scheduler(search_frequency_hours=frequency)
    yield
    stop_scheduler()


app = FastAPI(
    title="AI Job Pilot",
    description="Automated job search, matching and application agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api")
app.include_router(emails.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(referrals.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AI Job Pilot"}


@app.get("/api/dashboard")
def dashboard_summary():
    from agent.models.database import SessionLocal, Job, Application, Email, SearchRun, ApplicationStatus
    from sqlalchemy import desc
    db = SessionLocal()
    try:
        total_jobs = db.query(Job).count()
        matched = db.query(Job).filter(Job.match_score >= 0.7).count()
        applied = db.query(Application).filter(Application.status == ApplicationStatus.email_sent).count()
        interviews = db.query(Application).filter(Application.status == ApplicationStatus.interview).count()
        pending_emails = db.query(Email).filter(Email.status == "draft").count()
        last_run = db.query(SearchRun).order_by(desc(SearchRun.started_at)).first()
        top_jobs = (
            db.query(Job)
            .filter(Job.match_score >= 0.7)
            .order_by(desc(Job.match_score))
            .limit(5)
            .all()
        )
        return {
            "stats": {
                "total_jobs_found": total_jobs,
                "jobs_matched": matched,
                "applications_sent": applied,
                "interviews": interviews,
                "pending_review": pending_emails,
            },
            "last_run": {
                "started_at": last_run.started_at.isoformat() if last_run else None,
                "status": last_run.status if last_run else None,
                "jobs_found": last_run.jobs_found if last_run else 0,
            } if last_run else None,
            "top_matches": [
                {
                    "id": j.id, "title": j.title, "company": j.company,
                    "match_score": j.match_score, "source": j.source,
                    "url": j.url,
                }
                for j in top_jobs
            ],
        }
    finally:
        db.close()
