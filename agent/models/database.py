from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, Boolean, JSON, ForeignKey, Enum as SAEnum
)
from sqlalchemy import event, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import enum
import logging
import os

from agent.utils import utcnow

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobpilot.db")

if "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,           # wait up to 30s for a lock before failing
        },
        # Default pool size — WAL mode + busy_timeout handle concurrency
    )
    # Enable WAL mode for much better read/write concurrency
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30s busy timeout in ms
        cursor.close()
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ApplicationStatus(str, enum.Enum):
    found = "found"
    matched = "matched"
    draft_ready = "draft_ready"
    email_sent = "email_sent"
    applied = "applied"
    rejected = "rejected"
    interview = "interview"
    offer = "offer"
    skipped = "skipped"
    expired = "expired"      # removed by quality control: dead link, closed, too old, duplicate


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    description = Column(Text)
    url = Column(String)
    source = Column(String)  # linkedin, indeed, seek, glassdoor, etc.
    salary_min = Column(Float)
    salary_max = Column(Float)
    salary_currency = Column(String)
    job_type = Column(String)  # full-time, part-time, contract
    remote = Column(Boolean, default=False)
    match_score = Column(Float, index=True)
    match_reasons = Column(JSON)
    skills_matched = Column(JSON)
    skills_missing = Column(JSON)
    posted_at = Column(DateTime)
    found_at = Column(DateTime, default=utcnow, index=True)
    status = Column(SAEnum(ApplicationStatus), default=ApplicationStatus.found, index=True)
    is_referral_post = Column(Boolean, default=False)
    referral_contact = Column(String)
    url_valid = Column(Boolean, nullable=True)  # None=unchecked, True=reachable, False=broken
    qc_reason = Column(String)                  # why quality control removed it
    qc_checked_at = Column(DateTime)            # last time QC opened the posting

    application = relationship("Application", back_populates="job", uselist=False)
    emails = relationship("Email", back_populates="job")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True)
    status = Column(SAEnum(ApplicationStatus), default=ApplicationStatus.draft_ready)
    cover_letter = Column(Text)
    custom_resume_notes = Column(Text)
    applied_at = Column(DateTime)
    follow_up_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    job = relationship("Job", back_populates="application")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    email_type = Column(String)  # application, referral_request, follow_up, cold_email
    to_address = Column(String, nullable=True)   # nullable: referral drafts don't always have address yet
    to_name = Column(String)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, default="draft", index=True)  # draft, sending, sent, failed, archived
    gmail_message_id = Column(String)
    gmail_thread_id = Column(String)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    error_message = Column(Text)

    job = relationship("Job", back_populates="emails")


class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    location = Column(String)
    linkedin_url = Column(String)
    github_url = Column(String)
    portfolio_url = Column(String)
    resume_text = Column(Text)
    resume_filename = Column(String)
    skills = Column(JSON, default=lambda: [])
    years_experience = Column(Integer)
    education = Column(JSON, default=lambda: [])
    work_history = Column(JSON, default=lambda: [])
    visa_status = Column(String)          # e.g. "Australian PR", "Student Visa", "Citizen", "Sponsored"
    work_rights = Column(String)          # e.g. "Full working rights", "Limited hours"
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class JobPreferences(Base):
    __tablename__ = "job_preferences"

    id = Column(Integer, primary_key=True, index=True)
    job_titles = Column(JSON, default=lambda: [])       # ["Software Engineer", "Backend Developer"]
    keywords = Column(JSON, default=lambda: [])          # ["Python", "FastAPI", "AWS"]
    exclude_keywords = Column(JSON, default=lambda: [])  # ["senior", "10+ years"]
    locations = Column(JSON, default=lambda: [])         # ["Sydney", "Remote"]
    remote_only = Column(Boolean, default=False)
    min_salary = Column(Float)
    max_salary = Column(Float)
    job_types = Column(JSON, default=lambda: [])         # ["full-time", "contract"]
    experience_levels = Column(JSON, default=lambda: []) # ["entry", "mid"]
    sources = Column(JSON, default=lambda: [])           # which job boards to search
    min_match_score = Column(Float, default=0.6)
    auto_send_above_score = Column(Float, default=0.85)  # auto-send if score >= this
    max_applications_per_day = Column(Integer, default=10)
    search_frequency_hours = Column(Integer, default=6)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime)
    jobs_found = Column(Integer, default=0)
    jobs_matched = Column(Integer, default=0)
    emails_drafted = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    sources_searched = Column(JSON, default=lambda: [])
    error_message = Column(Text)
    status = Column(String, default="running")  # running, completed, failed


class ReferralProfile(Base):
    """
    Details the referral agent uses in forum posts. Any field left empty is
    filled from the parsed resume (UserProfile) and job preferences.
    """
    __tablename__ = "referral_profile"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    headline = Column(String)                 # "Cybersecurity grad, SOC / blue team"
    email = Column(String)
    phone = Column(String)
    location = Column(String)
    linkedin_url = Column(String)
    github_url = Column(String)
    portfolio_url = Column(String)
    target_roles = Column(JSON, default=lambda: [])
    target_companies = Column(JSON, default=lambda: [])
    skills = Column(JSON, default=lambda: [])
    years_experience = Column(Integer)
    work_rights = Column(String)
    availability = Column(String)             # "Immediately", "From Dec 2026"
    pitch = Column(Text)                      # 2-3 sentence intro in your words
    # privacy: what the agent may put in public posts
    share_email = Column(Boolean, default=False)
    share_phone = Column(Boolean, default=False)
    share_linkedin = Column(Boolean, default=True)
    # where + how
    platforms = Column(JSON, default=lambda: ["reddit", "linkedin", "glassdoor"])
    subreddits = Column(JSON, default=lambda: ["forhire", "cscareerquestionsOCE", "auscorp"])
    auto_discover = Column(Boolean, default=True)   # find threads during each search run
    max_posts_per_day = Column(Integer, default=5)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ForumPost(Base):
    """A drafted forum post or reply. Nothing is posted until you approve it."""
    __tablename__ = "forum_posts"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)   # platform+thread+kind
    platform = Column(String, nullable=False)                # reddit, linkedin, glassdoor
    kind = Column(String, nullable=False)                    # open_to_work, reply_hiring, reply_referral
    target = Column(String)                                  # subreddit / community for new posts
    thread_url = Column(String)
    thread_title = Column(String)
    thread_author = Column(String)
    thread_snippet = Column(Text)
    relevance = Column(Float)
    title = Column(String)
    body = Column(Text, nullable=False)
    status = Column(String, default="draft", index=True)  # draft, approved, posting, posted, failed, dismissed, expired
    error_message = Column(Text)
    posted_url = Column(String)
    found_via = Column(String)                # firecrawl, agent_browser
    created_at = Column(DateTime, default=utcnow)
    posted_at = Column(DateTime)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Additive, idempotent migrations for databases created by older versions.
# create_all() adds new tables but never touches existing ones.
_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN url_valid BOOLEAN",
    "ALTER TABLE jobs ADD COLUMN qc_reason VARCHAR",
    "ALTER TABLE jobs ADD COLUMN qc_checked_at DATETIME",
    "CREATE INDEX IF NOT EXISTS ix_jobs_found_at ON jobs (found_at)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_match_score ON jobs (match_score)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs (status)",
    "CREATE INDEX IF NOT EXISTS ix_emails_status ON emails (status)",
    "CREATE INDEX IF NOT EXISTS ix_forum_posts_status ON forum_posts (status)",
]


def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for stmt in _MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()  # column / index already exists
