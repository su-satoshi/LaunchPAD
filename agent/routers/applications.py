from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from agent.utils import utcnow

from agent.models.database import get_db, Application, Job, ApplicationStatus, SearchRun

router = APIRouter(prefix="/applications", tags=["applications"])


class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = Field(None, max_length=20_000)
    follow_up_at: Optional[datetime] = None


@router.get("")
def list_applications(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Application).join(Job)
    if status:
        q = q.filter(Application.status == status)
    total = q.count()
    apps = q.order_by(desc(Application.created_at)).offset((page - 1) * limit).limit(limit).all()
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "applications": [_app_dict(a) for a in apps],
    }


@router.get("/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(404, "Application not found")
    return _app_dict(app)


@router.patch("/{app_id}")
def update_application(app_id: int, data: ApplicationUpdate, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(404, "Application not found")
    if data.status:
        app.status = data.status
        if app.job:
            app.job.status = data.status
    if data.notes is not None:
        app.notes = data.notes
    if data.follow_up_at is not None:
        app.follow_up_at = data.follow_up_at
    app.updated_at = utcnow()
    db.commit()
    return _app_dict(app)


@router.get("/stats/pipeline")
def pipeline_stats(db: Session = Depends(get_db)):
    # One GROUP BY instead of a COUNT query per stage
    counts = dict(db.query(Application.status, func.count(Application.id)).group_by(Application.status).all())
    result = {s.value: counts.get(s, 0) for s in ApplicationStatus}

    recent_runs = db.query(SearchRun).order_by(desc(SearchRun.started_at)).limit(5).all()
    return {
        "pipeline": result,
        "recent_runs": [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "jobs_found": r.jobs_found,
                "jobs_matched": r.jobs_matched,
                "emails_sent": r.emails_sent,
                "status": r.status,
            }
            for r in recent_runs
        ],
    }


def _app_dict(a: Application) -> dict:
    job = a.job
    return {
        "id": a.id,
        "job_id": a.job_id,
        "status": a.status,
        "notes": a.notes,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "follow_up_at": a.follow_up_at.isoformat() if a.follow_up_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "job": {
            "title": job.title, "company": job.company,
            "location": job.location, "url": job.url,
            "source": job.source, "match_score": job.match_score,
        } if job else None,
    }
