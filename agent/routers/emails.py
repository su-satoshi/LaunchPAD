from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from agent.models.database import get_db, Email, Job, Application, ApplicationStatus, UserProfile
from agent.ai.claude_agent import draft_application_email
from agent.gmail_service.gmail_service import send_email

router = APIRouter(prefix="/emails", tags=["emails"])


class SendEmailRequest(BaseModel):
    to_address: Optional[str] = None
    to_name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class DraftEmailRequest(BaseModel):
    job_id: int
    email_type: str = "application"
    recipient_name: Optional[str] = None
    to_address: Optional[str] = None
    additional_context: Optional[str] = None


@router.get("")
def list_emails(
    status: Optional[str] = None,
    email_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(Email)
    if status:
        q = q.filter(Email.status == status)
    if email_type:
        q = q.filter(Email.email_type == email_type)
    total = q.count()
    emails = q.order_by(desc(Email.created_at)).offset((page - 1) * limit).limit(limit).all()
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "emails": [_email_dict(e) for e in emails],
    }


@router.get("/{email_id}")
def get_email(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(404, "Email not found")
    return _email_dict(email)


@router.patch("/{email_id}")
def update_email(email_id: int, data: SendEmailRequest, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(404, "Email not found")
    if email.status == "sent":
        raise HTTPException(400, "Cannot edit sent email")
    if data.to_address is not None:
        email.to_address = data.to_address
    if data.to_name is not None:
        email.to_name = data.to_name
    if data.subject is not None:
        email.subject = data.subject
    if data.body is not None:
        email.body = data.body
    db.commit()
    return _email_dict(email)


@router.post("/{email_id}/send")
def send_draft(email_id: int, overrides: Optional[SendEmailRequest] = None, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(404, "Email not found")
    if email.status == "sent":
        raise HTTPException(400, "Email already sent")

    profile = db.query(UserProfile).first()
    to_address = (overrides.to_address if overrides else None) or email.to_address
    if not to_address:
        raise HTTPException(400, "No recipient email address set")

    subject = (overrides.subject if overrides else None) or email.subject
    body = (overrides.body if overrides else None) or email.body
    to_name = (overrides.to_name if overrides else None) or email.to_name

    try:
        result = send_email(
            to_address=to_address,
            subject=subject,
            body=body,
            to_name=to_name,
            from_name=profile.name if profile else None,
        )
        email.status = "sent"
        email.sent_at = datetime.utcnow()
        email.gmail_message_id = result.get("message_id")
        email.gmail_thread_id = result.get("thread_id")
        email.to_address = to_address

        if email.job_id:
            job = db.query(Job).filter(Job.id == email.job_id).first()
            if job:
                job.status = ApplicationStatus.email_sent
                app = db.query(Application).filter(Application.job_id == job.id).first()
                if not app:
                    app = Application(job_id=job.id, status=ApplicationStatus.email_sent, applied_at=datetime.utcnow())
                    db.add(app)
                else:
                    app.status = ApplicationStatus.email_sent
                    app.applied_at = datetime.utcnow()

        db.commit()
        return {"ok": True, "message_id": result.get("message_id")}
    except Exception as e:
        email.error_message = str(e)
        db.commit()
        raise HTTPException(500, f"Send failed: {e}")


@router.post("/draft")
async def create_draft_email(req: DraftEmailRequest, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == req.job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    profile = db.query(UserProfile).first()
    if not profile or not profile.resume_text:
        raise HTTPException(400, "Upload your resume first")

    profile_dict = {
        "name": profile.name, "email": profile.email,
        "phone": profile.phone, "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url, "portfolio_url": profile.portfolio_url,
    }
    job_dict = {
        "title": job.title, "company": job.company, "location": job.location,
        "url": job.url, "description": job.description,
    }
    import asyncio
    email_data = await asyncio.to_thread(
        draft_application_email,
        job=job_dict,
        resume_text=profile.resume_text,
        user_profile=profile_dict,
        email_type=req.email_type,
        recipient_name=req.recipient_name,
    )
    to_address = req.to_address or email_data.get("suggested_to_address", "")

    email_obj = Email(
        job_id=job.id,
        email_type=req.email_type,
        to_address=to_address or None,
        to_name=email_data.get("suggested_to_name", req.recipient_name or "Hiring Manager"),
        subject=email_data.get("subject", ""),
        body=email_data.get("body", ""),
        status="draft",
    )
    db.add(email_obj)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(503, f"Database busy — try again in a moment: {e}")
    db.refresh(email_obj)
    return _email_dict(email_obj)


@router.delete("/{email_id}")
def delete_email(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(404, "Email not found")
    if email.status == "sent":
        raise HTTPException(400, "Cannot delete sent email")
    db.delete(email)
    db.commit()
    return {"ok": True}


def _email_dict(e: Email) -> dict:
    return {
        "id": e.id,
        "job_id": e.job_id,
        "email_type": e.email_type,
        "to_address": e.to_address,
        "to_name": e.to_name,
        "subject": e.subject,
        "body": e.body,
        "status": e.status,
        "gmail_message_id": e.gmail_message_id,
        "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "error_message": e.error_message,
    }
