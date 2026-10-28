"""Shared test setup.

Tests run without real API keys: the model clients only need a key to be
present when they're created, and no test calls a model or a sandbox.
"""

import os
import shutil

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the SQL tools at a throwaway copy of the Chinook database."""
    from tools import sql

    db = tmp_path / "chinook.db"
    shutil.copy(sql.DB_PATH, db)
    monkeypatch.setattr(sql, "DB_PATH", db)
    monkeypatch.setattr(sql, "_READ_ONLY_URI", f"file:{db}?mode=ro")
    return db


@pytest.fixture
def temp_mailbox(tmp_path, monkeypatch):
    """Point the mail store at a throwaway mailbox file."""
    import mail_store

    monkeypatch.setattr(mail_store, "_STORE_PATH", tmp_path / "mail_store.json")
    return mail_store
