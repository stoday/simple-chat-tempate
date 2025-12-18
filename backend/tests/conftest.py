import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Provide a fresh FastAPI TestClient with isolated DB/uploads per test module."""
    db_path = tmp_path / "test_simplechat.db"
    upload_root = tmp_path / "chat_uploads"
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("SIMPLECHAT_DB_PATH", str(db_path))
    monkeypatch.setenv("CHAT_UPLOAD_ROOT", str(upload_root))

    import backend.database as database
    import backend.main as main

    importlib.reload(database)
    importlib.reload(main)

    with TestClient(main.app) as test_client:
        yield test_client
