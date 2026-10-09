from unittest.mock import patch

from agent.models.database import ApplicationStatus, Email, ForumPost, Job, UserProfile
from agent.utils import utcnow


def _job(db, **kw):
    j = Job(external_id=kw.pop("external_id", f"id-{utcnow().timestamp()}-{kw.get('title','x')}"),
            title=kw.pop("title", "SOC Analyst"), company=kw.pop("company", "Acme"),
            url=kw.pop("url", "https://example.com/job"), **kw)
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


# ── request guard ────────────────────────────────────────────────────────────

def test_cross_site_post_is_blocked(client):
    r = client.post("/api/jobs/search/trigger", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/jobs/search/trigger", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_dns_rebinding_host_is_blocked(client):
    r = client.get("/api/health", headers={"Host": "attacker.example"})
    assert r.status_code == 403


def test_same_origin_requests_work(client):
    assert client.get("/api/health").json()["status"] == "ok"
    r = client.get("/api/jobs", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200


# ── jobs ─────────────────────────────────────────────────────────────────────

def test_jobs_list_paging_is_bounded(client):
    assert client.get("/api/jobs?limit=501").status_code == 422
    assert client.get("/api/jobs?page=0").status_code == 422
    assert client.get("/api/jobs?limit=500").status_code == 200


def test_invalid_job_status_rejected(client, db):
    j = _job(db)
    assert client.patch(f"/api/jobs/{j.id}/status?status=hacked").status_code == 400
    assert client.patch(f"/api/jobs/{j.id}/status?status=interview").status_code == 200
    assert client.get(f"/api/jobs/{j.id}").json()["status"] == "interview"


def test_unsafe_job_url_not_rendered(client, db):
    j = _job(db, url="javascript:alert(1)")
    assert client.get(f"/api/jobs/{j.id}").json()["url"] is None


def test_search_status_and_stats(client, db):
    _job(db, match_score=0.8, status=ApplicationStatus.matched)
    s = client.get("/api/jobs/search/status").json()
    assert set(s) == {"is_running", "jobs_found", "jobs_scored", "jobs_matched"}
    stats = client.get("/api/jobs/stats/summary").json()
    assert stats["total_found"] == 1 and stats["by_status"] == {"matched": 1}


def test_bulk_apply_rejects_internal_urls(client, db):
    db.add(UserProfile(name="Test", resume_text="resume"))
    db.commit()
    r = client.post("/api/jobs/bulk-apply", json={"url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 400
    r = client.post("/api/jobs/bulk-apply", json={"url": "file:///etc/passwd"})
    assert r.status_code == 400


def test_qc_endpoints(client):
    assert client.get("/api/jobs/qc/status").json()["running"] is False


# ── emails ───────────────────────────────────────────────────────────────────

def test_send_requires_valid_address(client, db):
    e = Email(subject="Hi", body="Body", status="draft", to_address=None)
    db.add(e)
    db.commit()
    r = client.post(f"/api/emails/{e.id}/send", json={"to_address": "not-an-email"})
    assert r.status_code == 400


def test_send_marks_sent_and_blocks_double_send(client, db):
    e = Email(subject="Hi", body="Body", status="draft", to_address="hr@example.com")
    db.add(e)
    db.commit()
    with patch("agent.routers.emails.send_email", return_value={"message_id": "m1", "thread_id": "t1"}) as send:
        assert client.post(f"/api/emails/{e.id}/send").status_code == 200
        assert client.post(f"/api/emails/{e.id}/send").status_code == 400
        assert send.call_count == 1


def test_failed_send_returns_to_draft(client, db):
    e = Email(subject="Hi", body="Body", status="draft", to_address="hr@example.com")
    db.add(e)
    db.commit()
    with patch("agent.routers.emails.send_email", side_effect=RuntimeError("Gmail not connected")):
        assert client.post(f"/api/emails/{e.id}/send").status_code == 502
    db.refresh(e)
    assert e.status == "draft" and "Gmail" in e.error_message


# ── applications ─────────────────────────────────────────────────────────────

def test_pipeline_counts_every_stage(client):
    p = client.get("/api/applications/stats/pipeline").json()["pipeline"]
    assert set(p) == {s.value for s in ApplicationStatus}


# ── referrals ────────────────────────────────────────────────────────────────

def test_referral_profile_falls_back_to_resume(client, db):
    db.add(UserProfile(name="Jane", email="jane@example.com", skills=["SIEM"], resume_text="cv"))
    db.commit()
    d = client.get("/api/referrals/profile").json()
    assert d["values"]["full_name"] == "Jane" and d["sources"]["full_name"] == "resume"
    d = client.put("/api/referrals/profile", json={"full_name": "Jane C", "platforms": ["reddit", "bogus"]}).json()
    assert d["sources"]["full_name"] == "saved" and d["settings"]["platforms"] == ["reddit"]


def test_forum_post_guards(client, db):
    p = ForumPost(external_id="x1", platform="reddit", kind="reply_hiring", body="Hello", status="posted")
    db.add(p)
    db.commit()
    assert client.patch(f"/api/referrals/posts/{p.id}", json={"body": "edit"}).status_code == 400
    assert client.post(f"/api/referrals/posts/{p.id}/approve").status_code == 400
    p2 = ForumPost(external_id="x2", platform="reddit", kind="reply_hiring", body="Hello", status="draft")
    db.add(p2)
    db.commit()
    assert client.patch(f"/api/referrals/posts/{p2.id}", json={"status": "posted"}).status_code == 400
