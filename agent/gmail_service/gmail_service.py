"""
Gmail API service for sending and managing job application emails.
Uses OAuth2 — run `python -m agent.gmail_service.gmail_service` once to authorise.
"""
import base64
import json
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", "./gmail_token.json"))
CREDENTIALS_PATH = Path(os.getenv("GMAIL_CREDENTIALS_PATH", "./gmail_credentials.json"))


def _get_service():
    """Return an authenticated Gmail API service."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Install Google API libraries: pip install google-api-python-client google-auth-oauthlib"
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
            except Exception as e:
                logger.warning(f"Gmail token refresh failed: {e}")
                raise RuntimeError("Gmail token expired — re-authenticate via Settings → Connect Gmail.")
        else:
            # Never auto-open browser during background tasks.
            # Require explicit user action: Settings → Connect Gmail.
            raise RuntimeError(
                "Gmail not connected. Open Settings → Gmail section → Connect Gmail."
            )

    return build("gmail", "v1", credentials=creds)


def send_email(
    to_address: str,
    subject: str,
    body: str,
    to_name: Optional[str] = None,
    from_name: Optional[str] = None,
) -> dict:
    """Send an email via Gmail API. Returns {message_id, thread_id}."""
    service = _get_service()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    display_to = f"{to_name} <{to_address}>" if to_name else to_address
    msg["To"] = display_to

    from_email = os.getenv("GMAIL_FROM_ADDRESS", "")
    if from_name and from_email:
        msg["From"] = f"{from_name} <{from_email}>"
    elif from_email:
        msg["From"] = from_email

    # plain text
    msg.attach(MIMEText(body, "plain"))
    # html version
    html_body = body.replace("\n", "<br>")
    msg.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    return {
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
    }


def create_draft(
    to_address: str,
    subject: str,
    body: str,
    to_name: Optional[str] = None,
    from_name: Optional[str] = None,
) -> dict:
    """Create a Gmail draft (does not send). Returns {draft_id, message_id}."""
    service = _get_service()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    display_to = f"{to_name} <{to_address}>" if to_name else to_address
    msg["To"] = display_to

    from_email = os.getenv("GMAIL_FROM_ADDRESS", "")
    if from_name and from_email:
        msg["From"] = f"{from_name} <{from_email}>"

    msg.attach(MIMEText(body, "plain"))
    html_body = body.replace("\n", "<br>")
    msg.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()

    return {
        "draft_id": result.get("id"),
        "message_id": result.get("message", {}).get("id"),
    }


def list_recent_sent(max_results: int = 20) -> list[dict]:
    """List recent sent emails (for tracking)."""
    service = _get_service()
    results = service.users().messages().list(
        userId="me", labelIds=["SENT"], maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    items = []
    for m in messages:
        detail = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "To", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        items.append({
            "message_id": m["id"],
            "subject": headers.get("Subject", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
        })
    return items


def authorize():
    """Run this once interactively to generate gmail_token.json."""
    print("Starting Gmail OAuth2 authorization...")
    _get_service()
    print(f"✓ Gmail authorized. Token saved to {TOKEN_PATH}")


if __name__ == "__main__":
    authorize()
