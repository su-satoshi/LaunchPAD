"""
Gmail API service for sending and managing job application emails.
Uses OAuth2 — run `python -m agent.gmail_service.gmail_service` once to authorise.
"""
import base64
import html
import logging
import os
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Optional

from agent.utils import one_line

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
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "Install Google API libraries: pip install google-api-python-client google-auth-oauthlib"
        ) from e

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_token(creds.to_json())
            except Exception as e:
                logger.warning(f"Gmail token refresh failed: {e}")
                raise RuntimeError("Gmail token expired — re-authenticate via Settings → Connect Gmail.") from e
        else:
            # Never auto-open browser during background tasks.
            # Require explicit user action: Settings → Connect Gmail.
            raise RuntimeError(
                "Gmail not connected. Open Settings → Gmail section → Connect Gmail."
            )

    return build("gmail", "v1", credentials=creds)


def _save_token(token_json: str) -> None:
    """The token grants access to your mailbox: write it readable by you only."""
    TOKEN_PATH.write_text(token_json)
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def _build_message(to_address: str, subject: str, body: str,
                   to_name: Optional[str], from_name: Optional[str]) -> str:
    """
    Build the MIME message. Header values are stripped of CR/LF (no header
    injection) and the HTML part is escaped, so text written by the model or
    copied from a job ad can't smuggle markup or links into your email.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = one_line(subject, 300)
    to_address = one_line(to_address, 320)
    msg["To"] = formataddr((one_line(to_name, 120), to_address)) if to_name else to_address
    from_email = one_line(os.getenv("GMAIL_FROM_ADDRESS", ""), 320)
    if from_email:
        msg["From"] = formataddr((one_line(from_name, 120), from_email)) if from_name else from_email
    msg.attach(MIMEText(body, "plain"))
    html_body = html.escape(body).replace("\n", "<br>")
    msg.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_email(
    to_address: str,
    subject: str,
    body: str,
    to_name: Optional[str] = None,
    from_name: Optional[str] = None,
) -> dict:
    """Send an email via Gmail API. Returns {message_id, thread_id}."""
    service = _get_service()
    raw = _build_message(to_address, subject, body, to_name, from_name)
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"message_id": result.get("id"), "thread_id": result.get("threadId")}


def create_draft(
    to_address: str,
    subject: str,
    body: str,
    to_name: Optional[str] = None,
    from_name: Optional[str] = None,
) -> dict:
    """Create a draft in your Gmail Drafts folder (does not send). Returns {draft_id, message_id}."""
    service = _get_service()
    raw = _build_message(to_address, subject, body, to_name, from_name)
    result = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return {"draft_id": result.get("id"), "message_id": result.get("message", {}).get("id")}


def gmail_ready() -> bool:
    return TOKEN_PATH.exists()


# ── Connect Gmail (OAuth) ────────────────────────────────────────────────────

_oauth_lock = threading.Lock()


def start_oauth() -> str:
    """
    Start Google's sign-in flow and return the URL to open. A one-shot local
    server on a random port receives Google's redirect and saves the token.
    The same Flow object issues the URL and receives the code, so the OAuth
    `state` check passes (generating a second URL would break it).
    """
    from wsgiref.simple_server import WSGIRequestHandler, make_server
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError("gmail_credentials.json not found - download it from Google Cloud Console")
    if not _oauth_lock.acquire(blocking=False):
        raise RuntimeError("A Gmail sign-in is already in progress - finish it in the open tab")

    try:
        received: dict = {}

        def _app(environ, start_response):
            from wsgiref.util import request_uri
            received["uri"] = request_uri(environ)
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [b"<html><body style='font-family:sans-serif'>Gmail connected. "
                    b"You can close this tab and go back to Orion.</body></html>"]

        class _Quiet(WSGIRequestHandler):
            def log_message(self, *args):
                pass

        server = make_server("localhost", 0, _app, handler_class=_Quiet)
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        flow.redirect_uri = f"http://localhost:{server.server_port}/"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    except BaseException:
        _oauth_lock.release()
        raise

    def _wait():
        try:
            server.timeout = 300           # give up after 5 minutes
            server.handle_request()
            if "uri" in received:
                # oauthlib insists on https; the local redirect is plain http by design
                flow.fetch_token(authorization_response=received["uri"].replace("http://", "https://", 1))
                _save_token(flow.credentials.to_json())
                logger.info("Gmail connected - token saved")
        except Exception as e:
            logger.error(f"Gmail sign-in failed: {e}")
        finally:
            server.server_close()
            _oauth_lock.release()

    threading.Thread(target=_wait, daemon=True).start()
    return auth_url


def authorize():
    """CLI helper: python -m agent.gmail_service.gmail_service"""
    import webbrowser
    url = start_oauth()
    print(f"Opening Google sign-in...\n{url}")
    webbrowser.open(url)


if __name__ == "__main__":
    authorize()
