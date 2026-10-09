"""
Referral agent.

  discover_threads()   Finds posts on Reddit / LinkedIn / Glassdoor Community
                       where people are hiring or offering referrals for your
                       target roles (Firecrawl search + the browser agent),
                       then Claude drafts a reply to each relevant one.

  compose_open_to_work()  Drafts an "I'm looking, can anyone refer me" post
                       for each platform from your referral details.

  publish_post()       Posts ONE approved draft through the Stagehand browser,
                       using your own signed-in Chrome profile.

Nothing is ever posted without you approving the draft first.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus, urlparse

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.models.database import (
    SessionLocal, ForumPost, ReferralProfile, UserProfile, JobPreferences,
)
from agent.tools import firecrawl_client

logger = logging.getLogger(__name__)

PLATFORMS: dict[str, dict] = {
    "reddit": {
        "label": "Reddit",
        "login_url": "https://www.reddit.com/login/",
        "search_url": "https://www.reddit.com/search/?q={q}&type=posts&sort=new&t=month",
        "domains": ["reddit.com"],
    },
    "linkedin": {
        "label": "LinkedIn",
        "login_url": "https://www.linkedin.com/login",
        "search_url": "https://www.linkedin.com/search/results/content/?keywords={q}&sortBy=%22date_posted%22",
        "domains": ["linkedin.com"],
    },
    "glassdoor": {
        "label": "Glassdoor Community",
        "login_url": "https://www.glassdoor.com/profile/login_input.htm",
        "search_url": "https://www.glassdoor.com/Community/index.htm",
        "domains": ["glassdoor.com", "glassdoor.com.au"],
    },
}

_discover_lock = asyncio.Lock()
_discover_state: dict = {"running": False, "last_run": None, "last_result": None}


def discover_state() -> dict:
    return {**_discover_state, "running": _discover_lock.locked()}


# ── Profile: saved details, falling back to resume + preferences ─────────────

PROFILE_FIELDS = [
    "full_name", "headline", "email", "phone", "location", "linkedin_url", "github_url",
    "portfolio_url", "target_roles", "target_companies", "skills", "years_experience",
    "work_rights", "availability", "pitch",
]
SETTINGS_FIELDS = ["share_email", "share_phone", "share_linkedin", "platforms", "subreddits",
                   "auto_discover", "max_posts_per_day"]


def get_or_create_profile(db: Session) -> ReferralProfile:
    rp = db.query(ReferralProfile).first()
    if not rp:
        rp = ReferralProfile()
        db.add(rp)
        db.commit()
        db.refresh(rp)
    return rp


def effective_profile(db: Session) -> dict:
    """
    Returns {"values": {...}, "sources": {field: saved|resume|preferences|missing}, "settings": {...}}.
    Saved referral details win; empty ones fall back to the resume, then preferences.
    """
    rp = get_or_create_profile(db)
    up = db.query(UserProfile).first()
    pr = db.query(JobPreferences).first()

    fallback_resume = {
        "full_name": getattr(up, "name", None),
        "email": getattr(up, "email", None),
        "phone": getattr(up, "phone", None),
        "location": getattr(up, "location", None),
        "linkedin_url": getattr(up, "linkedin_url", None),
        "github_url": getattr(up, "github_url", None),
        "portfolio_url": getattr(up, "portfolio_url", None),
        "skills": getattr(up, "skills", None),
        "years_experience": getattr(up, "years_experience", None),
        "work_rights": " / ".join(x for x in [getattr(up, "visa_status", None),
                                              getattr(up, "work_rights", None)] if x) or None,
    }
    fallback_prefs = {
        "target_roles": getattr(pr, "job_titles", None),
        "location": ", ".join(getattr(pr, "locations", None) or []) or None,
        "skills": getattr(pr, "keywords", None),
    }

    values, sources = {}, {}
    for f in PROFILE_FIELDS:
        saved = getattr(rp, f, None)
        if _filled(saved):
            values[f], sources[f] = saved, "saved"
        elif _filled(fallback_resume.get(f)):
            values[f], sources[f] = fallback_resume[f], "resume"
        elif _filled(fallback_prefs.get(f)):
            values[f], sources[f] = fallback_prefs[f], "preferences"
        else:
            values[f], sources[f] = ([] if f in ("target_roles", "target_companies", "skills") else None), "missing"

    settings = {f: getattr(rp, f) for f in SETTINGS_FIELDS}
    required = ["full_name", "target_roles", "location", "skills"]
    missing = [f for f in required if sources[f] == "missing"]
    return {"values": values, "sources": sources, "settings": settings,
            "missing_required": missing, "has_resume": bool(up and up.resume_text)}


def _filled(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def public_profile(db: Session) -> dict:
    """Only what the user allowed in public posts."""
    eff = effective_profile(db)
    v, s = dict(eff["values"]), eff["settings"]
    if not s.get("share_email"):
        v.pop("email", None)
    if not s.get("share_phone"):
        v.pop("phone", None)
    if not s.get("share_linkedin"):
        v.pop("linkedin_url", None)
    return v


# ── Claude writing ───────────────────────────────────────────────────────────

_WRITER_RULES = """Writing rules:
- Write as the candidate, first person, warm and specific, no hype or buzzwords.
- Never invent experience, employers, certifications or numbers that are not in the profile.
- Only include contact details that appear in the profile below (others are private).
- Keep it short: forum readers skim. No hashtags unless the platform is LinkedIn (max 3).
- Never ask for money, never offer payment for referrals, no spam phrasing."""


def _claude_json(prompt: str, max_tokens: int = 3000):
    from agent.ai.claude_agent import client, MODEL
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _draft_open_to_work(profile: dict, platform: str, target: Optional[str]) -> dict:
    norms = {
        "reddit": f"Reddit text post for r/{target}. Follow that subreddit's usual format "
                  f"(r/forhire titles must start with '[For Hire]'). Plain text, 120-200 words.",
        "linkedin": "LinkedIn feed post announcing you're open to roles and asking your network "
                    "for referrals or intros. 80-150 words, line breaks between short paragraphs.",
        "glassdoor": "Glassdoor Community post (in a careers / referrals bowl) asking members at "
                     "target companies for a referral. 80-140 words.",
    }[platform]
    prompt = f"""Draft a post where the candidate says they are looking for work and asks for referrals.
Platform: {norms}
{_WRITER_RULES}

Candidate profile (JSON):
{json.dumps(profile, default=str, indent=1)}

Return ONLY JSON: {{"title": "<post title, or empty string for LinkedIn>", "body": "<post text>"}}"""
    return _claude_json(prompt, 1500)


def _triage_and_reply(candidates: list[dict], profile: dict) -> list[dict]:
    listing = "\n\n".join(
        f"[{i}] platform={c['platform']} url={c['url']}\nTITLE: {c.get('title','')}\n"
        f"AUTHOR: {c.get('author','')}\nTEXT: {c.get('snippet','')[:1200]}"
        for i, c in enumerate(candidates)
    )
    prompt = f"""You help a job seeker find forum posts worth replying to.
For each post decide:
- kind: "hiring" (someone is hiring / sharing an opening), "offering_referral" (someone offers to refer people),
  "seeking" (another job seeker), or "other".
- relevance 0-1: how well the opening/referral fits the candidate's target roles, skills and location.
- For hiring or offering_referral posts with relevance >= 0.5, write a reply comment from the candidate:
  2-5 sentences, mention 1-2 concrete matching skills, ask about next steps / a referral,
  and point to their LinkedIn if present. Otherwise reply = "".
{_WRITER_RULES}

Candidate profile (JSON):
{json.dumps(profile, default=str, indent=1)}

POSTS:
{listing}

Return ONLY a JSON array: [{{"index": 0, "kind": "...", "relevance": 0.0, "reply": "..."}}, ...]"""
    try:
        data = _claude_json(prompt, 4000)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Referral triage failed: {e}")
        return []


# ── Discovery ────────────────────────────────────────────────────────────────

class _Thread(BaseModel):
    title: str = ""
    url: str = Field("", description="absolute link to the post")
    author: str = ""
    snippet: str = Field("", description="first ~300 characters of the post text")


class _ThreadList(BaseModel):
    posts: list[_Thread] = Field(default_factory=list)


def _queries(profile: dict) -> list[str]:
    roles = (profile.get("target_roles") or [])[:3] or ["software engineer"]
    loc = (profile.get("location") or "").split(",")[0].strip()
    qs = []
    for r in roles:
        qs += [f'"{r}" referral', f'hiring "{r}" {loc}'.strip(), f'"can refer" {r} {loc}'.strip()]
    return qs


def _ext_id(platform: str, url: str, kind: str) -> str:
    return hashlib.md5(f"{platform}|{url.split('?')[0].rstrip('/')}|{kind}".encode()).hexdigest()


async def _firecrawl_candidates(platform: str, queries: list[str]) -> list[dict]:
    if not await firecrawl_client.is_available():
        return []
    domains = PLATFORMS[platform]["domains"]
    out = []
    for q in queries[:4]:
        for r in await firecrawl_client.search(q, limit=6, scrape=True, include_domains=domains):
            host = urlparse(r["url"]).netloc
            if not any(d in host for d in domains):
                continue
            out.append({"platform": platform, "url": r["url"], "title": r["title"],
                        "author": "", "snippet": (r["markdown"] or r["description"])[:1500],
                        "found_via": "firecrawl"})
    return out


async def _browser_candidates(platforms: list[str], queries: list[str]) -> list[dict]:
    from agent.tools.browser_agent import BrowserAgent
    out = []
    try:
        async with BrowserAgent() as agent:
            for platform in platforms:
                for q in queries[:2]:
                    try:
                        if platform == "glassdoor":
                            await agent.goto(PLATFORMS[platform]["search_url"])
                            if not agent.can_act:
                                continue
                            await agent.act(f"search the community posts for: {q}")
                        else:
                            await agent.goto(PLATFORMS[platform]["search_url"].format(q=quote_plus(q)))
                        res = await agent.extract(
                            "Extract the posts in these results where someone is hiring or offering "
                            "referrals. Skip ads and promoted posts.", _ThreadList)
                    except Exception as e:
                        logger.warning(f"Browser discovery failed on {platform}: {e}")
                        continue
                    for t in (res.posts if res else [])[:10]:
                        if t.url.startswith("http"):
                            out.append({"platform": platform, "url": t.url, "title": t.title,
                                        "author": t.author, "snippet": t.snippet,
                                        "found_via": "agent_browser"})
    except Exception as e:
        logger.warning(f"Browser agent unavailable for discovery: {e}")
    return out


async def discover_threads(platforms: Optional[list[str]] = None, use_browser: bool = True) -> dict:
    """Find hiring / referral threads and draft replies. Returns counts."""
    if _discover_lock.locked():
        return {"skipped": "already running"}
    async with _discover_lock:
        db = SessionLocal()
        try:
            eff = effective_profile(db)
            profile = public_profile(db)
            platforms = [p for p in (platforms or eff["settings"]["platforms"] or []) if p in PLATFORMS]
            queries = _queries(eff["values"])

            fc = await asyncio.gather(*[_firecrawl_candidates(p, queries) for p in platforms])
            candidates = [c for group in fc for c in group]
            if use_browser:
                candidates += await _browser_candidates(platforms, queries)

            # de-dupe against each other and against existing drafts
            existing = {e for (e,) in db.query(ForumPost.external_id).all()}
            uniq, seen = [], set()
            for c in candidates:
                key = c["url"].split("?")[0].rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                if any(_ext_id(c["platform"], c["url"], k) in existing
                       for k in ("reply_hiring", "reply_referral")):
                    continue
                uniq.append(c)
            uniq = uniq[:32]
            logger.info(f"Referral discovery: {len(candidates)} candidates, {len(uniq)} new")

            drafted = 0
            for i in range(0, len(uniq), 8):
                batch = uniq[i:i + 8]
                verdicts = await asyncio.to_thread(_triage_and_reply, batch, profile)
                for v in verdicts:
                    try:
                        c = batch[int(v.get("index"))]
                    except (TypeError, ValueError, IndexError):
                        continue
                    if v.get("kind") not in ("hiring", "offering_referral") or not v.get("reply"):
                        continue
                    if float(v.get("relevance") or 0) < 0.5:
                        continue
                    kind = "reply_hiring" if v["kind"] == "hiring" else "reply_referral"
                    db.add(ForumPost(
                        external_id=_ext_id(c["platform"], c["url"], kind),
                        platform=c["platform"], kind=kind, thread_url=c["url"],
                        thread_title=c.get("title", "")[:300], thread_author=c.get("author", "")[:120],
                        thread_snippet=c.get("snippet", "")[:2000], relevance=float(v["relevance"]),
                        body=v["reply"], found_via=c.get("found_via"),
                    ))
                    try:
                        db.commit()
                        drafted += 1
                    except Exception:
                        db.rollback()
            result = {"candidates": len(candidates), "new": len(uniq), "drafted": drafted,
                      "platforms": platforms}
            _discover_state.update(last_run=datetime.utcnow().isoformat(), last_result=result)
            return result
        finally:
            db.close()


def compose_open_to_work(db: Session, platforms: Optional[list[str]] = None) -> list[ForumPost]:
    eff = effective_profile(db)
    if eff["missing_required"]:
        raise ValueError(f"Fill in: {', '.join(eff['missing_required'])}")
    profile = public_profile(db)
    platforms = [p for p in (platforms or eff["settings"]["platforms"] or []) if p in PLATFORMS]
    created = []
    for p in platforms:
        targets = (eff["settings"].get("subreddits") or ["forhire"])[:3] if p == "reddit" else [None]
        for t in targets:
            draft = _draft_open_to_work(profile, p, t)
            post = ForumPost(
                external_id=_ext_id(p, f"new:{t or ''}:{datetime.utcnow().isoformat()}", "open_to_work"),
                platform=p, kind="open_to_work", target=t,
                title=(draft.get("title") or "")[:300], body=draft.get("body") or "",
            )
            db.add(post)
            created.append(post)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


# ── Publishing (one approved draft at a time) ────────────────────────────────

class _SignedIn(BaseModel):
    signed_in: bool = Field(description="true if a user is signed in on this site (avatar/profile menu visible, no sign-in prompt)")


def posted_today(db: Session, platform: str) -> int:
    since = datetime.utcnow() - timedelta(days=1)
    return db.query(ForumPost).filter(ForumPost.platform == platform, ForumPost.status == "posted",
                                      ForumPost.posted_at >= since).count()


def _first(locator):
    """Playwright exposes .first as a property, Stagehand as a method."""
    f = locator.first
    return f() if callable(f) else f


def _old_reddit(url: str) -> str:
    return re.sub(r"https?://(www\.|new\.)?reddit\.com", "https://old.reddit.com", url)


async def publish_post(post_id: int) -> None:
    from agent.tools.browser_agent import BrowserAgent, POST_HEADLESS
    db = SessionLocal()
    post = db.query(ForumPost).get(post_id)
    if not post:
        db.close()
        return
    post.status, post.error_message = "posting", None
    db.commit()
    try:
        async with BrowserAgent(headless=POST_HEADLESS) as agent:
            ok = await _publish(agent, post)
        post.status = "posted" if ok else "failed"
        if ok:
            post.posted_at = datetime.utcnow()
        else:
            post.error_message = post.error_message or "Couldn't confirm the post went through - check the site"
    except Exception as e:
        logger.error(f"Publishing post {post_id} failed: {e}")
        post.status, post.error_message = "failed", str(e)[:500]
    finally:
        db.commit()
        db.close()


async def _publish(agent, post: ForumPost) -> bool:
    p = post.platform
    body = post.body.strip()

    # Reddit: old.reddit has stable form fields, so this works even without Stagehand
    if p == "reddit":
        if post.kind == "open_to_work":
            await agent.goto(f"https://old.reddit.com/r/{post.target or 'forhire'}/submit?selftext=true")
            await _require_signed_in(agent, p)
            await agent.page.locator("textarea[name='title']").fill(post.title or "")
            await _first(agent.page.locator("textarea[name='text']")).fill(body)
            await agent.page.locator("button[name='submit']").click()
        else:
            await agent.goto(_old_reddit(post.thread_url))
            await _require_signed_in(agent, p)
            await _first(agent.page.locator("div.commentarea textarea[name='text']")).fill(body)
            await _first(agent.page.locator("div.commentarea button[type='submit']")).click()
        await asyncio.sleep(4)
        post.posted_url = await agent.current_url()
        return await _confirm(agent, body)

    if not agent.can_act:
        raise RuntimeError("Posting on LinkedIn/Glassdoor needs the Stagehand agent - install Google Chrome")

    if p == "linkedin":
        if post.kind == "open_to_work":
            await agent.goto("https://www.linkedin.com/feed/")
            await _require_signed_in(agent, p)
            await agent.act("click the 'Start a post' box at the top of the feed")
            if not await agent.fill("the text editor in the create-post dialog", body):
                raise RuntimeError("Couldn't find the post editor")
            await agent.act("click the 'Post' button in the create-post dialog")
        else:
            await agent.goto(post.thread_url)
            await _require_signed_in(agent, p)
            await agent.act("click the 'Comment' button under the main post")
            if not await agent.fill("the comment text box under the main post", body):
                raise RuntimeError("Couldn't find the comment box")
            await agent.act("click the button that submits the comment (usually 'Comment' or 'Post')")
    elif p == "glassdoor":
        if post.kind == "open_to_work":
            await agent.goto(PLATFORMS["glassdoor"]["search_url"])
            await _require_signed_in(agent, p)
            await agent.act("open the form to create a new community post")
            await agent.act("if asked to pick a community or bowl, choose one about job referrals, "
                            "careers or job hunting")
            if post.title:
                await agent.fill("the post title field, if there is one", post.title)
            if not await agent.fill("the main text box of the new post", body):
                raise RuntimeError("Couldn't find the post editor")
            await agent.act("click the button that publishes the post")
        else:
            await agent.goto(post.thread_url)
            await _require_signed_in(agent, p)
            await agent.act("click the comment or reply box under the post")
            if not await agent.fill("the comment text box", body):
                raise RuntimeError("Couldn't find the comment box")
            await agent.act("click the button that submits the comment")
    else:
        raise RuntimeError(f"Unknown platform {p}")

    await asyncio.sleep(4)
    post.posted_url = await agent.current_url()
    return await _confirm(agent, body)


async def _require_signed_in(agent, platform: str) -> None:
    res = await agent.extract("Is a user signed in on this site?", _SignedIn)
    if res is not None and not res.signed_in:
        raise RuntimeError(f"Not signed in to {PLATFORMS[platform]['label']} - use 'Connect' in "
                           f"Referrals > Forum posts first")


async def _confirm(agent, body: str) -> bool:
    text = re.sub(r"\s+", " ", await agent.page_text(60_000)).lower()
    probe = re.sub(r"\s+", " ", body).lower()[:60]
    return probe[:40] in text
