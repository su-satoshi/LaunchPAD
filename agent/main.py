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
# Status polling would otherwise fill the terminal with one access-log line every few seconds
logging.getLogger("uvicorn.access").addFilter(
    lambda record: "/api/jobs/search/status" not in record.getMessage()
)
logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
ALLOWED_HOSTS = {h.strip().lower() for h in os.getenv(
    "ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",") if h.strip()}


class LocalRequestGuard:
    """
    The API has no login: it's meant to be reached only by the dashboard on this
    computer. This blocks the two ways a web page you visit could still reach it:

      - DNS rebinding: a hostile domain that resolves to 127.0.0.1 (Host header check)
      - Cross-site "simple" requests: <form>/fetch(no-cors) POSTs that CORS doesn't
        stop, which could otherwise send emails or approve forum posts
        (Origin / Sec-Fetch-Site check on state-changing methods)
    """

    UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app, allowed_origins: list[str], allowed_hosts: set[str]):
        self.app = app
        self.allowed_origins = set(allowed_origins)
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        host = host[1:host.index("]")] if host.startswith("[") else host.rsplit(":", 1)[0]
        reason = None
        if host.lower() not in self.allowed_hosts:
            reason = "Host not allowed"
        elif scope["method"] in self.UNSAFE:
            origin = headers.get("origin")
            if origin and origin not in self.allowed_origins:
                reason = "Cross-origin request blocked"
            elif headers.get("sec-fetch-site") == "cross-site":
                reason = "Cross-site request blocked"
        if reason:
            logger.warning(f"Blocked {scope['method']} {scope['path']}: {reason}")
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"%s"}' % reason.encode()})
            return
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised")
    from agent.models.database import SessionLocal, JobPreferences
    db = SessionLocal()
    try:
        prefs = db.query(JobPreferences).first()
        frequency = (prefs.search_frequency_hours if prefs else None) or 6
    finally:
        db.close()
    start_scheduler(search_frequency_hours=frequency)
    yield
    stop_scheduler()


app = FastAPI(
    title="AI Job Pilot",
    description="Automated job search, matching and application agent",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.add_middleware(LocalRequestGuard, allowed_origins=ALLOWED_ORIGINS, allowed_hosts=ALLOWED_HOSTS)

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
