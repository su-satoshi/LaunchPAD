"""
Playwright-based auto-apply engine.

Strategy:
  1. Detect the job portal from the URL
  2. Log in with stored credentials (from .env) OR use a cached session
  3. Navigate to the apply page
  4. Fill all visible form fields from the user's profile
  5. Upload resume PDF if a file input exists
  6. Take a screenshot and return the result without submitting
     (user must confirm before final submit — safety gate)

Supported portals (expandable):
  - LinkedIn Easy Apply
  - Seek (Australia)
  - Indeed
  - Greenhouse (boards.greenhouse.io)
  - Lever (jobs.lever.co)
  - Generic fallback (best-effort form fill)
"""

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Optional

from agent.utils import host_matches

logger = logging.getLogger(__name__)

# ─── Credential helpers ───────────────────────────────────────────────────────

def _creds(portal: str) -> tuple[str, str]:
    """Read portal credentials from environment / .env file."""
    from dotenv import dotenv_values
    env = {**dotenv_values(), **os.environ}
    key = portal.upper().replace("-", "_")
    email    = env.get(f"{key}_EMAIL") or env.get("JOB_PORTAL_EMAIL") or ""
    password = env.get(f"{key}_PASSWORD") or env.get("JOB_PORTAL_PASSWORD") or ""
    return email, password


# Portal -> domains it legitimately lives on. Matching is on the parsed hostname
# (exact or subdomain), never a substring of the whole URL: a scraped link like
# https://evil.example/seek.com.au/login must not be treated as Seek.
PORTAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "linkedin":        ("linkedin.com",),
    "seek":            ("seek.com.au", "seek.co.nz"),
    "indeed":          ("indeed.com",),
    "greenhouse":      ("greenhouse.io",),
    "lever":           ("lever.co",),
    "workable":        ("workable.com",),
    "microsoft":       ("jobs.microsoft.com", "careers.microsoft.com"),
    "smartrecruiters": ("smartrecruiters.com",),
}


def _detect_portal(url: str) -> str:
    for portal, domains in PORTAL_DOMAINS.items():
        if host_matches(url, domains):
            return portal
    # indeed has country subdomains (au.indeed.com); covered by host_matches above
    return "generic"


def _on_portal(page_url: str, portal: str) -> bool:
    """Only ever type a portal password into that portal's own domain."""
    return host_matches(page_url, PORTAL_DOMAINS.get(portal, ()))


# ─── Session store (in-memory cache for browser contexts) ─────────────────────

_STORAGE_DIR = Path(__file__).parent / ".sessions"
_STORAGE_DIR.mkdir(exist_ok=True, mode=0o700)


def _session_path(portal: str) -> Path:
    return _STORAGE_DIR / f"{portal}_state.json"


# ─── Core auto-apply function ─────────────────────────────────────────────────

async def auto_apply_to_job(job: dict, profile) -> dict:
    """
    Attempt to auto-apply to a job. Returns:
      {
        success: bool,
        portal: str,
        status: "applied" | "needs_review" | "login_required" | "error",
        message: str,
        screenshot_b64: str,  # base64 PNG of the final state
        fields_filled: list[str],
        requires_confirmation: bool,  # always True — user must confirm submit
      }
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "portal": "unknown",
            "status": "error",
            "message": (
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium"
            ),
            "screenshot_b64": "",
            "fields_filled": [],
            "requires_confirmation": False,
        }

    url     = job.get("url", "")
    portal  = _detect_portal(url)
    session = _session_path(portal)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,           # Visible so user can monitor / confirm
            args=["--disable-blink-features=AutomationControlled"],
            slow_mo=80,              # Slight slow-mo looks more human
        )

        # Restore session if cached
        ctx_opts = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "locale": "en-AU",
        }
        if session.exists():
            ctx_opts["storage_state"] = str(session)

        context = await browser.new_context(**ctx_opts)
        page    = await context.new_page()

        try:
            result = await _apply_for_portal(page, portal, url, job, profile)

            # Save session (preserves cookies/localStorage for next run)
            await context.storage_state(path=str(session))
            try:
                os.chmod(session, 0o600)   # saved cookies = a signed-in session
            except OSError:
                pass

            # Take final screenshot
            screenshot = await page.screenshot(full_page=False)
            result["screenshot_b64"] = base64.b64encode(screenshot).decode()

        except Exception as e:
            logger.exception(f"Auto-apply error on {portal}")
            try:
                screenshot = await page.screenshot(full_page=False)
                ss_b64 = base64.b64encode(screenshot).decode()
            except Exception:
                ss_b64 = ""
            result = {
                "success": False,
                "portal": portal,
                "status": "error",
                "message": f"Unexpected error: {e}",
                "screenshot_b64": ss_b64,
                "fields_filled": [],
                "requires_confirmation": False,
            }
        finally:
            # Keep browser open for 3 s so user can see the result
            await asyncio.sleep(3)
            await context.close()
            await browser.close()

    return result


# ─── Portal-specific handlers ─────────────────────────────────────────────────

async def _apply_for_portal(page, portal: str, url: str, job: dict, profile) -> dict:
    """Route to the correct portal handler."""
    handlers = {
        "linkedin":        _apply_linkedin,
        "seek":            _apply_seek,
        "indeed":          _apply_indeed,
        "greenhouse":      _apply_greenhouse,
        "lever":           _apply_lever,
        "workable":        _apply_workable,
        "smartrecruiters": _apply_smartrecruiters,
    }
    handler = handlers.get(portal, _apply_generic)
    return await handler(page, url, job, profile)


# ── LinkedIn Easy Apply ───────────────────────────────────────────────────────

async def _apply_linkedin(page, url: str, job: dict, profile) -> dict:
    from playwright.async_api import TimeoutError as PWTimeout

    fields_filled: list[str] = []
    email, password = _creds("linkedin")

    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Check if logged in
    if "login" in page.url or "authwall" in page.url or await page.query_selector(".nav__button-secondary"):
        if not email or not password:
            return _needs_login("linkedin", "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in your .env file")
        # Login flow
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        if not _on_portal(page.url, "linkedin"):
            return _needs_review("linkedin", "Sign-in page isn't on linkedin.com - not entering your password")
        await page.fill("#username", email);  fields_filled.append("email")
        await page.fill("#password", password); fields_filled.append("password")
        await page.click('[type="submit"]')
        try:
            await page.wait_for_url("**/feed/**", timeout=15_000)
        except PWTimeout:
            return _needs_login("linkedin", "Login failed — check credentials or complete 2FA in the browser window")
        # Navigate back to the job
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Click Easy Apply button
    try:
        btn = await page.wait_for_selector("button.jobs-apply-button", timeout=8_000)
        await btn.click()
    except PWTimeout:
        # Might already be on an apply modal or the button label differs
        btn = await page.query_selector("[aria-label*='Easy Apply']")
        if btn:
            await btn.click()
        else:
            return _needs_review("linkedin", "Could not find Easy Apply button — job may require external application")

    await page.wait_for_timeout(1500)

    # Fill phone if asked
    phone_inp = await page.query_selector("input[id*='phone']")
    if phone_inp and profile.phone:
        await phone_inp.fill(str(profile.phone))
        fields_filled.append("phone")

    # Upload resume if file input visible
    await _upload_resume(page, profile, fields_filled)

    # Fill any open text inputs with sensible values
    await _fill_common_fields(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "linkedin",
        "status": "needs_review",
        "message": (
            "LinkedIn Easy Apply form opened and pre-filled. "
            "Review the form in the browser, then click Submit to complete."
        ),
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── Seek ──────────────────────────────────────────────────────────────────────

async def _apply_seek(page, url: str, job: dict, profile) -> dict:
    from playwright.async_api import TimeoutError as PWTimeout

    fields_filled: list[str] = []
    email, password = _creds("seek")

    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Click Apply button
    try:
        apply_btn = await page.wait_for_selector(
            "a[data-automation='job-detail-apply'], button[data-automation='job-detail-apply']",
            timeout=8_000,
        )
        await apply_btn.click()
        await page.wait_for_load_state("domcontentloaded")
    except PWTimeout:
        return _needs_review("seek", "Could not find Apply button on Seek page")

    # Login if redirected
    if "login" in page.url or "signin" in page.url:
        if not email or not password:
            return _needs_login("seek", "Set SEEK_EMAIL and SEEK_PASSWORD in your .env file")
        if not _on_portal(page.url, "seek"):
            return _needs_review("seek", "Sign-in page isn't on seek.com.au - not entering your password")
        email_inp = await page.query_selector("input[type='email'], input[name='email']")
        pass_inp  = await page.query_selector("input[type='password']")
        if email_inp:
            await email_inp.fill(email); fields_filled.append("email")
        if pass_inp:
            await pass_inp.fill(password); fields_filled.append("password")
        submit = await page.query_selector("button[type='submit']")
        if submit:
            await submit.click()
            await page.wait_for_load_state("domcontentloaded")

    # Fill application form fields
    await _fill_common_fields(page, profile, fields_filled)
    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "seek",
        "status": "needs_review",
        "message": "Seek application form opened and pre-filled. Review, then submit in the browser.",
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── Indeed ────────────────────────────────────────────────────────────────────

async def _apply_indeed(page, url: str, job: dict, profile) -> dict:
    from playwright.async_api import TimeoutError as PWTimeout

    fields_filled: list[str] = []
    email, password = _creds("indeed")

    # Indeed often uses "Easily Apply" — go directly to the job page
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Try clicking Apply Now
    try:
        btn = await page.wait_for_selector(
            "button[id*='apply'], a[id*='apply'], .ia-IndeedApplyButton",
            timeout=6_000,
        )
        await btn.click()
        await page.wait_for_timeout(2000)
    except PWTimeout:
        pass

    # Login if needed
    if "accounts.indeed.com" in page.url or "login" in page.url:
        if not email or not password:
            return _needs_login("indeed", "Set INDEED_EMAIL and INDEED_PASSWORD in your .env file")
        if not _on_portal(page.url, "indeed"):
            return _needs_review("indeed", "Sign-in page isn't on indeed.com - not entering your password")
        email_inp = await page.query_selector("input[type='email'], #ifl-InputFormField-3")
        if email_inp:
            await email_inp.fill(email); fields_filled.append("email")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1500)
        pass_inp = await page.query_selector("input[type='password']")
        if pass_inp:
            await pass_inp.fill(password); fields_filled.append("password")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

    await _fill_common_fields(page, profile, fields_filled)
    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "indeed",
        "status": "needs_review",
        "message": "Indeed application form opened and pre-filled. Review and confirm to submit.",
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── Greenhouse ────────────────────────────────────────────────────────────────

async def _apply_greenhouse(page, url: str, job: dict, profile) -> dict:
    """Greenhouse boards don't require login — direct form fill."""
    fields_filled: list[str] = []

    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Greenhouse fields by name/id
    field_map = {
        "first_name":  lambda: _first(profile.name),
        "last_name":   lambda: _last(profile.name),
        "email":       lambda: profile.email or "",
        "phone":       lambda: profile.phone or "",
        "location":    lambda: profile.location or "",
        "linkedin":    lambda: profile.linkedin_url or "",
        "website":     lambda: profile.portfolio_url or profile.github_url or "",
    }

    for fname, val_fn in field_map.items():
        val = val_fn()
        if not val:
            continue
        sel = f"input[name='{fname}'], input[id*='{fname}'], input[placeholder*='{fname}' i]"
        inp = await page.query_selector(sel)
        if inp:
            await inp.fill(val)
            fields_filled.append(fname)

    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "greenhouse",
        "status": "needs_review",
        "message": "Greenhouse form pre-filled. Review details then click Submit Application.",
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── Lever ─────────────────────────────────────────────────────────────────────

async def _apply_lever(page, url: str, job: dict, profile) -> dict:
    fields_filled: list[str] = []

    # Lever's apply page is usually the job URL + /apply
    apply_url = url.rstrip("/") + "/apply" if "/apply" not in url else url
    await page.goto(apply_url, wait_until="domcontentloaded", timeout=30_000)

    field_map = {
        "name":     lambda: profile.name or "",
        "email":    lambda: profile.email or "",
        "phone":    lambda: profile.phone or "",
        "org":      lambda: "",
        "urls[LinkedIn]": lambda: profile.linkedin_url or "",
        "urls[GitHub]":   lambda: profile.github_url or "",
        "urls[Portfolio]": lambda: profile.portfolio_url or "",
    }

    for fname, val_fn in field_map.items():
        val = val_fn()
        if not val:
            continue
        inp = await page.query_selector(f"input[name='{fname}']")
        if inp:
            await inp.fill(val)
            fields_filled.append(fname)

    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "lever",
        "status": "needs_review",
        "message": "Lever application form pre-filled. Review and submit.",
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── Workable ──────────────────────────────────────────────────────────────────

async def _apply_workable(page, url: str, job: dict, profile) -> dict:
    fields_filled: list[str] = []
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Click Apply button
    btn = await page.query_selector("button[data-ui='apply-button'], a[data-ui='apply-button']")
    if btn:
        await btn.click()
        await page.wait_for_timeout(1500)

    await _fill_common_fields(page, profile, fields_filled)
    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "workable",
        "status": "needs_review",
        "message": "Workable application form opened and pre-filled.",
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── SmartRecruiters ───────────────────────────────────────────────────────────

async def _apply_smartrecruiters(page, url: str, job: dict, profile) -> dict:
    fields_filled: list[str] = []
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    btn = await page.query_selector("button[data-label='apply'], a[data-label='apply']")
    if btn:
        await btn.click()
        await page.wait_for_timeout(1500)

    await _fill_common_fields(page, profile, fields_filled)
    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "smartrecruiters",
        "status": "needs_review",
        "message": "SmartRecruiters application form opened and pre-filled.",
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ── Generic fallback ──────────────────────────────────────────────────────────

async def _apply_generic(page, url: str, job: dict, profile) -> dict:
    fields_filled: list[str] = []
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Try to click any "Apply" button
    for sel in [
        "a[href*='apply' i]",
        "button:has-text('Apply')",
        "a:has-text('Apply Now')",
        "a:has-text('Apply for this job')",
    ]:
        btn = await page.query_selector(sel)
        if btn:
            await btn.click()
            await page.wait_for_timeout(2000)
            break

    await _fill_common_fields(page, profile, fields_filled)
    await _upload_resume(page, profile, fields_filled)

    return {
        "success": True,
        "portal": "generic",
        "status": "needs_review",
        "message": (
            f"Generic form fill attempted. "
            f"{len(fields_filled)} fields filled. "
            "Please review and submit manually in the browser."
        ),
        "fields_filled": fields_filled,
        "requires_confirmation": True,
        "screenshot_b64": "",
    }


# ─── Shared form-fill utilities ───────────────────────────────────────────────

async def _fill_common_fields(page, profile, filled: list[str]) -> None:
    """Best-effort fill for common form patterns across portals."""

    # Mapping: (selector_patterns, value_getter)
    rules = [
        (["input[name*='first' i][type='text']",
          "input[placeholder*='first name' i]",
          "input[id*='first_name' i]"],
         lambda: _first(profile.name)),

        (["input[name*='last' i][type='text']",
          "input[placeholder*='last name' i]",
          "input[id*='last_name' i]"],
         lambda: _last(profile.name)),

        (["input[name='name'][type='text']",
          "input[placeholder*='full name' i]",
          "input[id*='full_name' i]"],
         lambda: profile.name or ""),

        (["input[type='email']",
          "input[name='email']",
          "input[placeholder*='email' i]"],
         lambda: profile.email or ""),

        (["input[type='tel']",
          "input[name*='phone' i]",
          "input[placeholder*='phone' i]"],
         lambda: profile.phone or ""),

        (["input[name*='linkedin' i]",
          "input[placeholder*='linkedin' i]"],
         lambda: profile.linkedin_url or ""),

        (["input[name*='github' i]",
          "input[placeholder*='github' i]"],
         lambda: profile.github_url or ""),

        (["input[name*='portfolio' i]",
          "input[name*='website' i]",
          "input[placeholder*='portfolio' i]",
          "input[placeholder*='website' i]"],
         lambda: profile.portfolio_url or profile.github_url or ""),

        (["input[name*='location' i]",
          "input[placeholder*='location' i]",
          "input[placeholder*='city' i]"],
         lambda: profile.location or ""),
    ]

    for selectors, val_fn in rules:
        val = val_fn()
        if not val:
            continue
        for sel in selectors:
            inp = await page.query_selector(sel)
            if inp:
                try:
                    cur = await inp.input_value()
                    if cur:      # Don't overwrite pre-populated fields
                        break
                    await inp.fill(val)
                    filled.append(sel.split("[")[1].split("]")[0])  # rough field name
                except Exception:
                    pass
                break


async def _upload_resume(page, profile, filled: list[str]) -> None:
    """Find a file input and upload the resume PDF."""
    resume_path = _resume_path(profile)
    if not resume_path or not Path(resume_path).exists():
        return

    for sel in [
        "input[type='file'][accept*='pdf' i]",
        "input[type='file'][name*='resume' i]",
        "input[type='file'][name*='cv' i]",
        "input[type='file']",
    ]:
        inp = await page.query_selector(sel)
        if inp:
            try:
                await inp.set_input_files(resume_path)
                filled.append("resume_upload")
                break
            except Exception:
                pass


def _resume_path(profile) -> Optional[str]:
    """Return path to user's resume PDF file."""
    from dotenv import dotenv_values
    env = {**dotenv_values(), **os.environ}
    # Check explicit env var first
    path = env.get("RESUME_PDF_PATH") or ""
    if path and Path(path).exists():
        return path
    # Check profile's stored resume_filename
    fname = getattr(profile, "resume_filename", None)
    if fname:
        candidates = [
            Path(__file__).parent.parent / "uploads" / fname,
            Path(fname),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
    return None


# ─── Status builders ──────────────────────────────────────────────────────────

def _needs_login(portal: str, message: str) -> dict:
    return {
        "success": False,
        "portal": portal,
        "status": "login_required",
        "message": message,
        "screenshot_b64": "",
        "fields_filled": [],
        "requires_confirmation": False,
    }


def _needs_review(portal: str, message: str) -> dict:
    return {
        "success": False,
        "portal": portal,
        "status": "needs_review",
        "message": message,
        "screenshot_b64": "",
        "fields_filled": [],
        "requires_confirmation": True,
    }


def _first(name: Optional[str]) -> str:
    if not name:
        return ""
    parts = name.strip().split()
    return parts[0] if parts else ""


def _last(name: Optional[str]) -> str:
    if not name:
        return ""
    parts = name.strip().split()
    return parts[-1] if len(parts) > 1 else ""
