"""Test setup: isolated SQLite file, no real network, no scheduler."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="launchpad-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ["GMAIL_TOKEN_PATH"] = f"{_TMP}/gmail_token.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent.scheduler as scheduler  # noqa: E402

# Never start APScheduler in tests
scheduler.start_scheduler = lambda *a, **k: None
scheduler.stop_scheduler = lambda *a, **k: None

import agent.main as main  # noqa: E402
from agent.models.database import Base, SessionLocal, engine, init_db  # noqa: E402

main.start_scheduler = scheduler.start_scheduler
main.stop_scheduler = scheduler.stop_scheduler


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    with TestClient(main.app, base_url="http://testserver") as c:
        yield c
