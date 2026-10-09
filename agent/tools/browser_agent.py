"""
Agent-first browser built on Stagehand (github.com/browserbase/stagehand),
running 100% locally - no Browserbase account or API key.

Stagehand's Python SDK launches your installed Google Chrome, loads its
worker as a local extension, and uses Claude (your ANTHROPIC_API_KEY) to
understand pages: `act("click the reply button")`, `extract(...)`,
`observe(...)`. A persistent Chrome profile (.browser-data/) keeps you signed
in to LinkedIn / Reddit / Glassdoor between runs.

If Stagehand can't start (for example Chrome is missing or too old), the
agent falls back to plain Playwright + Claude reading the page text. The
fallback can read and extract, but it can't post - posting needs Stagehand.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(os.getenv("BROWSER_PROFILE_DIR", "./.browser-data")).resolve()
CHROME_PATH = os.getenv("CHROME_PATH") or None          # auto-detect when empty
AGENT_HEADLESS = os.getenv("AGENT_HEADLESS", "true").lower() != "false"
POST_HEADLESS = os.getenv("POST_HEADLESS", "false").lower() == "true"
STAGEHAND_MODEL = os.getenv("STAGEHAND_MODEL", "anthropic/claude-sonnet-4-6")

T = TypeVar("T", bound=BaseModel)

# One Chrome profile can only be opened by one browser at a time.
_profile_lock = asyncio.Lock()


def _anthropic_key() -> str:
    from dotenv import dotenv_values
    return dotenv_values().get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")


class BrowserAgentError(RuntimeError):
    pass


class BrowserAgent:
    """
    async with BrowserAgent() as agent:
        await agent.goto("https://example.com/careers")
        jobs = await agent.extract("every job listing on the page", JobList)
    """

    def __init__(self, headless: Optional[bool] = None, use_stagehand: bool = True):
        self.headless = AGENT_HEADLESS if headless is None else headless
        self.want_stagehand = use_stagehand
        self.mode: str = "none"        # "stagehand" | "playwright"
        self._browser = None           # stagehand StagehandBrowser
        self._stagehand = None
        self._pw = None
        self._pw_ctx = None
        self.page = None
        self._locked = False

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def __aenter__(self) -> "BrowserAgent":
        await _profile_lock.acquire()
        self._locked = True
        try:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            if self.want_stagehand and await self._start_stagehand():
                return self
            await self._start_playwright()
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def _start_stagehand(self) -> bool:
        key = _anthropic_key()
        if not key:
            logger.warning("ANTHROPIC_API_KEY missing - Stagehand needs it for act/extract")
            return False
        try:
            from stagehand import Stagehand, local_browser
        except ImportError:
            logger.warning("stagehand not installed - `pip install stagehand`")
            return False
        try:
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": str(PROFILE_DIR),
                "preserve_user_data_dir": True,
                "headless": self.headless,
                "viewport_width": 1366,
                "viewport_height": 900,
            }
            if CHROME_PATH:
                launch_kwargs["executable_path"] = CHROME_PATH
            self._browser = await local_browser.launch(**launch_kwargs)
            self._stagehand = await Stagehand.create(
                browser=self._browser,
                model=STAGEHAND_MODEL,
                model_api_key=key,
                self_heal=True,
            )
            pages = await self._browser.context.pages()
            self.page = pages[0] if pages else await self._browser.context.new_page()
            self.mode = "stagehand"
            logger.info("Browser agent: Stagehand (local Chrome)")
            return True
        except Exception as e:
            logger.warning(f"Stagehand failed to start ({e}) - falling back to Playwright")
            await self._close_stagehand()
            return False

    async def _start_playwright(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise BrowserAgentError("Neither Stagehand nor Playwright is available") from e
        self._pw = await async_playwright().start()
        opts: dict[str, Any] = {"headless": self.headless, "viewport": {"width": 1366, "height": 900}}
        if CHROME_PATH:
            opts["executable_path"] = CHROME_PATH
        try:
            # Prefer the real Chrome so the signed-in profile is shared with Stagehand
            self._pw_ctx = await self._pw.chromium.launch_persistent_context(
                str(PROFILE_DIR), channel=None if CHROME_PATH else "chrome", **opts
            )
        except Exception:
            self._pw_ctx = await self._pw.chromium.launch_persistent_context(str(PROFILE_DIR), **opts)
        self.page = self._pw_ctx.pages[0] if self._pw_ctx.pages else await self._pw_ctx.new_page()
        self.mode = "playwright"
        logger.info("Browser agent: Playwright fallback")

    async def _close_stagehand(self) -> None:
        for obj in (self._stagehand, self._browser):
            if obj is not None:
                try:
                    await obj.close()
                except Exception:
                    pass
        self._stagehand = None
        self._browser = None

    async def close(self) -> None:
        await self._close_stagehand()
        if self._pw_ctx is not None:
            try:
                await self._pw_ctx.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._pw_ctx = self._pw = None
        self.page = None
        if self._locked:
            self._locked = False
            _profile_lock.release()

    # ── primitives ───────────────────────────────────────────────────────────
    @property
    def can_act(self) -> bool:
        return self.mode == "stagehand"

    async def goto(self, url: str, timeout_ms: int = 45_000) -> None:
        if self.mode == "stagehand":
            await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        else:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await asyncio.sleep(2.0)  # let client-side apps render

    async def current_url(self) -> str:
        if self.mode == "stagehand":
            return await self.page.url()
        return self.page.url

    async def page_text(self, max_chars: int = 15_000) -> str:
        try:
            text = await self.page.evaluate("document.body ? document.body.innerText : ''")
        except Exception:
            text = ""
        return (text or "")[:max_chars]

    async def act(self, instruction: str, timeout_s: float = 60) -> bool:
        if not self.can_act:
            raise BrowserAgentError("This action needs the Stagehand agent (install Google Chrome)")
        try:
            res = await self._stagehand.act(instruction, timeout=float(timeout_s * 1000))
            await asyncio.sleep(1.2)
            data = getattr(res, "data", None)
            return bool(getattr(data, "success", True))
        except Exception as e:
            logger.warning(f"act failed: {instruction!r}: {e}")
            return False

    async def fill(self, target: str, text: str) -> bool:
        """Find an input/editor by description and type text into it."""
        if not self.can_act:
            raise BrowserAgentError("This action needs the Stagehand agent (install Google Chrome)")
        try:
            obs = await self._stagehand.observe(f"find {target}")
            for action in (obs.data or [])[:3]:
                try:
                    loc = self.page.locator(action.selector)
                    await loc.click()
                    try:
                        await loc.fill(text)
                    except Exception:
                        await loc.type(text)
                    await asyncio.sleep(0.5)
                    return True
                except Exception as e:
                    logger.debug(f"fill attempt failed on {action.selector}: {e}")
        except Exception as e:
            logger.warning(f"observe failed for {target!r}: {e}")
        # Last resort: let the agent type it (text passed as a variable, not in the prompt)
        return await self._act_with_text(f"type %text% into {target}", text)

    async def _act_with_text(self, instruction: str, text: str) -> bool:
        try:
            res = await self._stagehand.act(instruction, variables={"text": text})
            return bool(getattr(getattr(res, "data", None), "success", True))
        except Exception as e:
            logger.warning(f"act-with-text failed: {e}")
            return False

    async def extract(self, instruction: str, schema: Type[T]) -> Optional[T]:
        """Schema-validated extraction from the current page."""
        if self.mode == "stagehand":
            try:
                res = await self._stagehand.extract(instruction, schema, timeout=90_000.0)
                data = res.data
                return data if isinstance(data, schema) else schema.model_validate(data)
            except Exception as e:
                logger.warning(f"Stagehand extract failed ({e}) - reading page text instead")
        text = await self.page_text()
        if not text.strip():
            return None
        return await asyncio.to_thread(_claude_extract, instruction, text, schema)


def _claude_extract(instruction: str, page_text: str, schema: Type[T]) -> Optional[T]:
    """Fallback extraction: page text -> Claude -> schema."""
    from agent.ai.claude_agent import client, MODEL
    prompt = (
        f"{instruction}\n\nReturn ONLY JSON matching this JSON schema (no markdown):\n"
        f"{json.dumps(schema.model_json_schema())}\n\nPAGE TEXT:\n{page_text}"
    )
    try:
        resp = client.messages.create(model=MODEL, max_tokens=4096,
                                      messages=[{"role": "user", "content": prompt}])
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return schema.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"Claude fallback extract failed: {e}")
        return None


# ── Interactive sign-in ──────────────────────────────────────────────────────
# Opens a visible Chrome window on the profile so you can sign in by hand.
# The agent never sees or stores your password; only the browser cookies persist.

_login_task: Optional[asyncio.Task] = None
_login_state: dict[str, Any] = {"platform": None, "status": "idle"}
_login_done = asyncio.Event()


async def start_login(platform: str, url: str, max_minutes: int = 10) -> dict:
    global _login_task
    if _login_task and not _login_task.done():
        return {"ok": False, "detail": f"A sign-in window for {_login_state['platform']} is already open"}
    _login_done.clear()
    _login_state.update(platform=platform, status="opening")

    async def _run():
        try:
            async with BrowserAgent(headless=False, use_stagehand=False) as agent:
                await agent.goto(url)
                _login_state["status"] = "waiting_for_user"
                try:
                    await asyncio.wait_for(_login_done.wait(), timeout=max_minutes * 60)
                except asyncio.TimeoutError:
                    pass
            _login_state["status"] = "done"
        except Exception as e:
            logger.error(f"Sign-in window failed: {e}")
            _login_state.update(status="error", error=str(e))

    _login_task = asyncio.create_task(_run())
    return {"ok": True, "detail": f"Opening {platform} sign-in window on your computer"}


def finish_login() -> dict:
    _login_done.set()
    return {"ok": True, "platform": _login_state.get("platform")}


def login_state() -> dict:
    return dict(_login_state)


async def status() -> dict:
    """Cheap capability report for the Settings page (doesn't launch Chrome)."""
    try:
        import stagehand  # noqa: F401
        stagehand_installed = True
    except ImportError:
        stagehand_installed = False
    try:
        import playwright  # noqa: F401
        playwright_installed = True
    except ImportError:
        playwright_installed = False
    return {
        "stagehand_installed": stagehand_installed,
        "playwright_installed": playwright_installed,
        "profile_dir": str(PROFILE_DIR),
        "profile_exists": PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir()),
        "busy": _profile_lock.locked(),
        "model": STAGEHAND_MODEL,
    }
