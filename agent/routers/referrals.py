"""
Referrals API: your details, forum thread discovery, drafted posts, approve-to-post.
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from agent.models.database import get_db, ForumPost
from agent.referrals import agent as ref

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/referrals", tags=["referrals"])

from agent.utils import spawn as _spawn


# ── Details form ─────────────────────────────────────────────────────────────

class ReferralProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    headline: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    target_roles: Optional[list[str]] = None
    target_companies: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    years_experience: Optional[int] = None
    work_rights: Optional[str] = None
    availability: Optional[str] = None
    pitch: Optional[str] = None
    share_email: Optional[bool] = None
    share_phone: Optional[bool] = None
    share_linkedin: Optional[bool] = None
    platforms: Optional[list[str]] = None
    subreddits: Optional[list[str]] = None
    auto_discover: Optional[bool] = None
    max_posts_per_day: Optional[int] = None


@router.get("/profile")
def get_referral_profile(db: Session = Depends(get_db)):
    return ref.effective_profile(db)


@router.put("/profile")
def update_referral_profile(data: ReferralProfileUpdate, db: Session = Depends(get_db)):
    rp = ref.get_or_create_profile(db)
    for k, v in data.model_dump(exclude_unset=True).items():
        if k == "platforms" and v is not None:
            v = [p for p in v if p in ref.PLATFORMS]
        if k == "subreddits" and v is not None:
            v = [s.strip().removeprefix("r/").strip("/") for s in v if s.strip()]
        if k == "max_posts_per_day" and v is not None:
            v = max(1, min(int(v), 20))
        setattr(rp, k, v)
    db.commit()
    return ref.effective_profile(db)


@router.post("/profile/use-resume")
def reset_to_resume(db: Session = Depends(get_db)):
    """Clear saved overrides so every field falls back to the resume / preferences."""
    rp = ref.get_or_create_profile(db)
    for f in ref.PROFILE_FIELDS:
        setattr(rp, f, None)
    db.commit()
    return ref.effective_profile(db)


# ── Platforms + sign-in ──────────────────────────────────────────────────────

@router.get("/platforms")
async def platforms():
    from agent.tools import browser_agent, firecrawl_client
    return {
        "platforms": [{"id": k, "label": v["label"]} for k, v in ref.PLATFORMS.items()],
        "browser": await browser_agent.status(),
        "firecrawl": {"available": await firecrawl_client.is_available(),
                      "url": firecrawl_client.FIRECRAWL_URL},
        "login": browser_agent.login_state(),
        "discover": ref.discover_state(),
    }


@router.post("/login/{platform}")
async def open_login(platform: str):
    """Opens a visible Chrome window on this computer so you can sign in yourself."""
    if platform not in ref.PLATFORMS:
        raise HTTPException(404, "Unknown platform")
    from agent.tools import browser_agent
    return await browser_agent.start_login(platform, ref.PLATFORMS[platform]["login_url"])


@router.post("/login-done")
def login_done():
    from agent.tools import browser_agent
    return browser_agent.finish_login()


# ── Drafting ─────────────────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    platforms: Optional[list[str]] = None
    use_browser: bool = True


@router.post("/discover")
async def discover(req: DiscoverRequest):
    """Find hiring / referral threads and draft replies (runs in the background)."""
    if ref.discover_state()["running"]:
        return {"started": False, "detail": "Discovery already running"}
    _spawn(ref.discover_threads(req.platforms, use_browser=req.use_browser))
    return {"started": True}


class ComposeRequest(BaseModel):
    platforms: Optional[list[str]] = None


@router.post("/compose")
async def compose(req: ComposeRequest, db: Session = Depends(get_db)):
    """Draft 'open to work - can anyone refer me?' posts for each platform."""
    try:
        posts = await asyncio.to_thread(ref.compose_open_to_work, db, req.platforms)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.error(f"Compose failed: {e}")
        raise HTTPException(502, f"Drafting failed - check your Claude API key ({type(e).__name__})") from e
    return {"created": [_post_dict(p) for p in posts]}


# ── Post queue ───────────────────────────────────────────────────────────────

@router.get("/posts")
def list_posts(status: Optional[str] = None, platform: Optional[str] = None,
               db: Session = Depends(get_db)):
    q = db.query(ForumPost)
    if status:
        q = q.filter(ForumPost.status.in_(status.split(",")))
    else:
        q = q.filter(ForumPost.status.notin_(["dismissed", "expired"]))
    if platform:
        q = q.filter(ForumPost.platform == platform)
    posts = q.order_by(desc(ForumPost.created_at)).limit(200).all()
    counts = dict(db.query(ForumPost.status, func.count(ForumPost.id)).group_by(ForumPost.status).all())
    return {"posts": [_post_dict(p) for p in posts], "counts": counts}


class PostUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    target: Optional[str] = None
    status: Optional[str] = None   # only "dismissed" or "draft" from the UI


@router.patch("/posts/{post_id}")
def update_post(post_id: int, data: PostUpdate, db: Session = Depends(get_db)):
    post = db.get(ForumPost, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status in ("approved", "posting", "posted"):
        raise HTTPException(400, "This post is already going out")
    upd = data.model_dump(exclude_unset=True)
    if "status" in upd and upd["status"] not in ("dismissed", "draft"):
        raise HTTPException(400, "Use /approve to post")
    for k, v in upd.items():
        setattr(post, k, v)
    db.commit()
    return _post_dict(post)


@router.post("/posts/{post_id}/approve")
async def approve_post(post_id: int, db: Session = Depends(get_db)):
    """You approved this draft: the browser agent posts it from your signed-in profile."""
    post = db.get(ForumPost, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status in ("posting", "posted"):
        raise HTTPException(400, f"Already {post.status}")
    if not post.body.strip():
        raise HTTPException(400, "Post is empty")
    rp = ref.get_or_create_profile(db)
    cap = rp.max_posts_per_day or 5
    if ref.posted_today(db, post.platform) >= cap:
        raise HTTPException(429, f"Daily limit reached for {post.platform} ({cap}/day) - "
                                 f"posting too often gets accounts flagged")
    post.status = "approved"
    db.commit()
    _spawn(ref.publish_post(post_id))
    return _post_dict(post)


def _post_dict(p: ForumPost) -> dict:
    return {
        "id": p.id, "platform": p.platform, "kind": p.kind, "target": p.target,
        "thread_url": p.thread_url, "thread_title": p.thread_title,
        "thread_author": p.thread_author, "thread_snippet": p.thread_snippet,
        "relevance": p.relevance, "title": p.title, "body": p.body, "status": p.status,
        "error_message": p.error_message, "posted_url": p.posted_url, "found_via": p.found_via,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "posted_at": p.posted_at.isoformat() if p.posted_at else None,
    }
