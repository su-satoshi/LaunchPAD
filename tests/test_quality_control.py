from datetime import timedelta

import httpx
import pytest
import respx

import agent.quality_control as qc
from agent.models.database import ApplicationStatus, Email, ForumPost, Job, JobPreferences
from agent.utils import utcnow


@pytest.fixture(autouse=True)
def _public(monkeypatch):
    async def _yes(url):
        return True
    monkeypatch.setattr(qc, "is_public_url", _yes)


def _add(db, ext, **kw):
    j = Job(external_id=ext, title=kw.pop("title", "SOC Analyst"), company=kw.pop("company", ext),
            url=kw.pop("url", f"https://jobs.example/{ext}"), source=kw.pop("source", "seek"),
            status=kw.pop("status", ApplicationStatus.matched), match_score=kw.pop("match_score", 0.8),
            found_at=kw.pop("found_at", utcnow()), **kw)
    db.add(j)
    return j


@pytest.mark.asyncio
@respx.mock
async def test_quality_control_end_to_end(db):
    db.add(JobPreferences(exclude_keywords=["senior"], min_match_score=0.6, job_types=["full-time"]))
    keep = _add(db, "keep")
    _add(db, "kw", title="Senior SOC Analyst")
    _add(db, "low", match_score=0.4)
    _add(db, "old", posted_at=utcnow() - timedelta(days=60))
    dup_a = _add(db, "dupA", company="Same Co", match_score=0.9, url="https://jobs.example/a")
    _add(db, "dupB", company="Same Co", match_score=0.7, url="https://jobs.example/b", source="indeed")
    _add(db, "dead")
    _add(db, "closed")
    _add(db, "type", job_type="Contract")
    _add(db, "applied", status=ApplicationStatus.email_sent, posted_at=utcnow() - timedelta(days=90))
    _add(db, "js", url="javascript:alert(1)")
    db.commit()
    db.add(Email(job_id=db.query(Job).filter_by(external_id="closed").one().id, subject="s", body="b", status="draft"))
    db.add(ForumPost(external_id="t1", platform="reddit", kind="reply_hiring", body="hi", status="draft",
                     thread_snippet="UPDATE: filled, thanks all"))
    db.add(ForumPost(external_id="t2", platform="reddit", kind="reply_hiring", body="hi", status="draft",
                     created_at=utcnow() - timedelta(days=30)))
    db.commit()

    respx.get("https://jobs.example/dead").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example/closed").mock(
        return_value=httpx.Response(200, text="<h1>SOC</h1><p>This job is no longer accepting applications.</p>"))
    respx.get(url__regex=r"https://jobs\.example/.*").mock(return_value=httpx.Response(200, text="<p>Apply now</p>"))

    result = await qc.run_quality_control()
    db.expire_all()
    status = {j.external_id: j.status for j in db.query(Job)}

    assert status["keep"] == ApplicationStatus.matched
    assert status["kw"] == ApplicationStatus.skipped
    assert status["low"] == ApplicationStatus.skipped
    assert status["type"] == ApplicationStatus.skipped
    assert status["old"] == ApplicationStatus.expired
    assert status["dupA"] == ApplicationStatus.matched and status["dupB"] == ApplicationStatus.expired
    assert status["dead"] == ApplicationStatus.expired
    assert status["closed"] == ApplicationStatus.expired
    assert status["js"] == ApplicationStatus.expired
    assert status["applied"] == ApplicationStatus.email_sent          # your pipeline is never touched
    assert db.query(Email).one().status == "archived"
    assert {p.status for p in db.query(ForumPost)} == {"expired"}
    assert result["removed_total"] >= 9
    assert keep.id and dup_a.id


@pytest.mark.asyncio
@respx.mock
async def test_unreachable_once_is_not_expired(db):
    _add(db, "flaky")
    db.commit()
    respx.get("https://jobs.example/flaky").mock(side_effect=httpx.ConnectError("boom"))
    await qc.run_quality_control()
    db.expire_all()
    j = db.query(Job).one()
    assert j.status == ApplicationStatus.matched and j.url_valid is False


@pytest.mark.asyncio
async def test_real_listing_beats_search_link_duplicate(db):
    _add(db, "link", company="Google", source="top_companies", match_score=0.95)
    _add(db, "real", company="Google", source="indeed", match_score=0.70)
    db.commit()
    await qc.run_quality_control(check_pages=False)
    db.expire_all()
    status = {j.external_id: j.status for j in db.query(Job)}
    assert status["real"] == ApplicationStatus.matched
    assert status["link"] == ApplicationStatus.expired
