import importlib
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Provide a fresh FastAPI TestClient with isolated DB/uploads per test module."""
    db_path = tmp_path / "test_simplechat.db"
    backend_root = Path(__file__).resolve().parents[1]
    upload_directory = TemporaryDirectory(prefix=".test-chat-uploads-", dir=backend_root)
    upload_root = Path(upload_directory.name)
    rag_upload_directory = TemporaryDirectory(prefix=".test-rag-uploads-", dir=backend_root)
    rag_upload_root = Path(rag_upload_directory.name)
    monkeypatch.setenv("SECRET_KEY", "testsecret")
    monkeypatch.setenv("SIMPLECHAT_DB_PATH", str(db_path))
    monkeypatch.setenv("CHAT_UPLOAD_ROOT", str(upload_root))
    monkeypatch.setenv("RAG_UPLOAD_ROOT", str(rag_upload_root))

    import backend.database as database
    import backend.main as main

    importlib.reload(database)
    importlib.reload(main)

    class DefaultFakeAgent:
        def __call__(self, *, question: str, include_thinking: bool = False):
            yield {"type": "answer", "data": f"Test response: {question}"}

    def get_fake_agent(stream=True):
        with sqlite3.connect(db_path) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'message_event'"
            ).fetchone()
        assert table is not None, "database schema must exist before agent initialization"
        return DefaultFakeAgent()

    monkeypatch.setattr(main, "get_agent", get_fake_agent)
    monkeypatch.setattr(main, "SIMULATED_REPLY_DELAY", 0)

    try:
        with TestClient(main.app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        upload_directory.cleanup()
        rag_upload_directory.cleanup()
