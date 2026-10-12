"""
Fixtures for the code-level white-box suite (no browser).

These tests import the backend modules directly and call their functions,
so every branch can be driven with exact inputs, including ones the UI can
never produce. The database is a throwaway SQLite file selected through
FC_DB_PATH *before* the backend's `database` module is imported.
"""

import os
import sys
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="fc_whitebox_")
os.environ["FC_DB_PATH"] = os.path.join(_TMP_DIR, "unit_test.db")

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (BACKEND_DIR, TESTS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import seed_data  # noqa: E402

database.Base.metadata.create_all(bind=database.engine)


@pytest.fixture
def db():
    """A session on an emptied database."""
    session = database.SessionLocal()
    seed_data.clear_all_data(session)
    yield session
    session.close()


@pytest.fixture
def client(db):
    """FastAPI TestClient for backend/main.py (runs in-process, no server)."""
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


# --- small factories ------------------------------------------------------

@pytest.fixture
def make_tag(db):
    import crud

    def _make(name, color_hex="#667EEA", emoji="🏷️"):
        return crud.create_tag(db, schemas.TagCreate(name=name, color_hex=color_hex, emoji=emoji))
    return _make


@pytest.fixture
def make_rule(db):
    import crud

    def _make(keyword, tag_id=None, is_ignore_rule=False):
        return crud.create_rule(db, schemas.RuleCreate(
            account_keyword=keyword, tag_id=tag_id, is_ignore_rule=is_ignore_rule))
    return _make


@pytest.fixture
def make_tx(db):
    import crud

    def _make(amount, account_name="Shop", **kw):
        return crud.create_transaction(db, schemas.TransactionCreate(
            amount=amount, account_name=account_name, **kw))
    return _make
