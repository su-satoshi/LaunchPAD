import base64
import email

from agent.auto_apply.playwright_apply import _detect_portal, _on_portal
from agent.gmail_service.gmail_service import _build_message


def test_portal_detection_uses_real_hostname():
    assert _detect_portal("https://www.seek.com.au/job/123") == "seek"
    assert _detect_portal("https://au.indeed.com/viewjob?jk=1") == "indeed"
    assert _detect_portal("https://evil.example/seek.com.au/login") == "generic"
    assert not _on_portal("https://evil.example/login?next=seek.com.au", "seek")
    assert _on_portal("https://login.seek.com.au/", "seek")


def test_email_message_is_header_safe_and_html_escaped(monkeypatch):
    monkeypatch.setenv("GMAIL_FROM_ADDRESS", "me@example.com")
    raw = _build_message("hr@example.com", "Hello\r\nBcc: x@evil.com", "<script>alert(1)</script>\nThanks",
                         "HR\nTeam", "Me")
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw))
    assert msg["Bcc"] is None
    assert "\n" not in msg["Subject"]
    html_part = [p for p in msg.walk() if p.get_content_type() == "text/html"][0].get_payload(decode=True).decode()
    assert "<script>" not in html_part and "&lt;script&gt;" in html_part
