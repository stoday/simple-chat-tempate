from types import SimpleNamespace

from fastapi.testclient import TestClient

from .utils import auth_header, login_user, register_user


def _admin_headers(client: TestClient) -> dict:
    register_user(client, "admin@example.com", "password123", "Admin")
    token = login_user(client, "admin@example.com", "password123")
    return auth_header(token)


def test_build_index_uses_configured_models_and_persists_success(
    client: TestClient, monkeypatch
):
    import backend.main as main

    headers = _admin_headers(client)
    captured = {}

    class FakeRag:
        def __init__(self, **kwargs):
            captured["rag_options"] = kwargs

        def __call__(self, *, data_sources, prompt):
            captured["data_sources"] = data_sources
            captured["prompt"] = prompt
            return "ok"

    class FakeSummary:
        def __init__(self, **kwargs):
            captured["summary_options"] = kwargs

        def __call__(self, *, content):
            return "Test summary"

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=FakeRag, summary=FakeSummary),
    )

    config = client.patch(
        "/api/admin/llm-config",
        json={
            "model_name": "openai:gpt-4o-mini",
            "embedding_model": "openai:text-embedding-3-small",
        },
        headers=headers,
    )
    assert config.status_code == 200

    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201
    file_id = uploaded.json()[0]["id"]

    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id], "rebuild": False},
        headers=headers,
    )
    assert indexed.status_code == 200

    files = client.get("/api/admin/rag-files", headers=headers).json()
    assert files[0]["index_status"] == "indexed"
    assert files[0]["indexed_embedding_model"] == "openai:text-embedding-3-small"
    assert files[0]["summary"] == "Test summary"
    assert captured["rag_options"]["model"] == "openai:gpt-4o-mini"
    assert captured["rag_options"]["embeddings"] == "openai:text-embedding-3-small"
    assert captured["summary_options"]["model"] == "openai:gpt-4o-mini"


def test_failed_index_attempt_is_persisted(client: TestClient, monkeypatch):
    import backend.main as main

    headers = _admin_headers(client)

    class FailingRag:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, data_sources, prompt):
            raise RuntimeError("embedding service unavailable")

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=FailingRag, summary=lambda **kwargs: None),
    )

    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    file_id = uploaded.json()[0]["id"]

    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id], "rebuild": False},
        headers=headers,
    )
    assert indexed.status_code == 500

    files = client.get("/api/admin/rag-files", headers=headers).json()
    assert files[0]["index_status"] == "failed"
    assert files[0]["index_error"] == "embedding service unavailable"


def test_changing_embedding_model_requires_rebuild(client: TestClient, monkeypatch):
    import backend.main as main

    headers = _admin_headers(client)

    class SuccessfulRag:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, data_sources, prompt):
            return "ok"

    class SuccessfulSummary:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, content):
            return "Test summary"

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=SuccessfulRag, summary=SuccessfulSummary),
    )
    client.patch(
        "/api/admin/llm-config",
        json={"embedding_model": "openai:text-embedding-3-small"},
        headers=headers,
    )
    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    file_id = uploaded.json()[0]["id"]
    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id]},
        headers=headers,
    )
    assert indexed.status_code == 200

    changed = client.patch(
        "/api/admin/llm-config",
        json={"embedding_model": "gemini:gemini-embedding-001"},
        headers=headers,
    )
    assert changed.status_code == 200

    files = client.get("/api/admin/rag-files", headers=headers).json()
    assert files[0]["index_status"] == "rebuild_required"
    assert files[0]["indexed_embedding_model"] == "openai:text-embedding-3-small"


def test_searchable_sources_include_only_currently_indexed_files(
    client: TestClient, monkeypatch
):
    import backend.main as main
    from backend.rag_library import get_searchable_rag_sources

    headers = _admin_headers(client)

    class SuccessfulRag:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, data_sources, prompt):
            return "ok"

    class SuccessfulSummary:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, content):
            return "Test summary"

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=SuccessfulRag, summary=SuccessfulSummary),
    )
    client.patch(
        "/api/admin/llm-config",
        json={"embedding_model": "openai:text-embedding-3-small"},
        headers=headers,
    )
    uploaded = client.post(
        "/api/admin/rag-files",
        files=[
            ("files", ("indexed.txt", b"Indexed", "text/plain")),
            ("files", ("pending.txt", b"Pending", "text/plain")),
        ],
        headers=headers,
    )
    file_ids = [item["id"] for item in uploaded.json()]
    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_ids[0]]},
        headers=headers,
    )
    assert indexed.status_code == 200

    with main.get_connection() as db:
        sources = get_searchable_rag_sources(
            db, main.RAG_UPLOAD_ROOT, "openai:text-embedding-3-small"
        )

    assert len(sources) == 1
    assert sources[0].name.endswith("indexed.txt")


def test_agent_registers_document_tool_only_when_sources_are_searchable(
    client: TestClient, monkeypatch
):
    import backend.main as main
    import backend.tools as tools

    headers = _admin_headers(client)
    captured = []

    def fake_agents(**kwargs):
        captured.append(kwargs)
        return object()

    fake_akasha = SimpleNamespace(
        agents=fake_agents,
        create_tool=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(tools, "akasha", fake_akasha)

    tools.build_agent(stream=False)
    assert not any(
        tool.get("tool_name") == "documents_rag_tool"
        for tool in captured[-1]["tools"]
        if isinstance(tool, dict)
    )

    class SuccessfulRag:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, data_sources, prompt):
            return "ok"

    class SuccessfulSummary:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, content):
            return "Test summary"

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=SuccessfulRag, summary=SuccessfulSummary),
    )
    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [uploaded.json()[0]["id"]]},
        headers=headers,
    )
    assert indexed.status_code == 200

    tools.build_agent(stream=False)
    assert any(
        tool.get("tool_name") == "documents_rag_tool"
        for tool in captured[-1]["tools"]
        if isinstance(tool, dict)
    )


def test_build_index_skips_already_indexed_files(client: TestClient, monkeypatch):
    import backend.main as main

    headers = _admin_headers(client)
    calls = {"rag": 0}

    class CountingRag:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, data_sources, prompt):
            calls["rag"] += 1
            return "ok"

    class SuccessfulSummary:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, content):
            return "Test summary"

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=CountingRag, summary=SuccessfulSummary),
    )
    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    file_id = uploaded.json()[0]["id"]

    first = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id]},
        headers=headers,
    )
    assert first.status_code == 200
    assert calls["rag"] == 1

    second = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id]},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["file_ids"] == []
    assert calls["rag"] == 1


def test_summary_failure_does_not_undo_successful_index(client: TestClient, monkeypatch):
    import backend.main as main

    headers = _admin_headers(client)

    class SuccessfulRag:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *, data_sources, prompt):
            return "ok"

    def failing_summary(**kwargs):
        raise RuntimeError("summary service unavailable")

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=SuccessfulRag, summary=failing_summary),
    )
    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    file_id = uploaded.json()[0]["id"]

    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id]},
        headers=headers,
    )
    assert indexed.status_code == 200

    file = client.get("/api/admin/rag-files", headers=headers).json()[0]
    assert file["index_status"] == "indexed"
    assert file["summary_error"] == "summary service unavailable"


def test_rag_adapter_creation_failure_is_persisted(client: TestClient, monkeypatch):
    import backend.main as main

    headers = _admin_headers(client)

    class FailingRag:
        def __init__(self, **kwargs):
            raise RuntimeError("embedding credentials missing")

    monkeypatch.setattr(
        main,
        "akasha",
        SimpleNamespace(RAG=FailingRag, summary=lambda **kwargs: None),
    )
    uploaded = client.post(
        "/api/admin/rag-files",
        files={"files": ("handbook.txt", b"Warranty policy", "text/plain")},
        headers=headers,
    )
    file_id = uploaded.json()[0]["id"]

    indexed = client.post(
        "/api/admin/rag-files/index",
        json={"file_ids": [file_id]},
        headers=headers,
    )
    assert indexed.status_code == 500
    file = client.get("/api/admin/rag-files", headers=headers).json()[0]
    assert file["index_status"] == "failed"
    assert file["index_error"] == "embedding credentials missing"


def test_rag_query_rebuilds_instance_when_configured_model_changes(
    client: TestClient, monkeypatch
):
    import backend.main as main
    import backend.rag_state as rag_state
    import backend.tools as tools

    headers = _admin_headers(client)
    client.patch(
        "/api/admin/llm-config",
        json={
            "model_name": "openai:gpt-4o-mini",
            "embedding_model": "openai:text-embedding-3-small",
        },
        headers=headers,
    )
    captured = {}

    class FakeRag:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __call__(self, *, data_sources, prompt):
            return "fresh response"

    class OldRag:
        def __call__(self, *, data_sources, prompt):
            raise AssertionError("stale RAG instance was used")

    rag_state.set_rag_instance(
        OldRag(), ["old.txt"], "gemini:old-model", "gemini:old-embedding"
    )
    monkeypatch.setattr(tools, "akasha", SimpleNamespace(RAG=FakeRag))
    monkeypatch.setattr(tools, "_build_rag_data_sources", lambda: ["fresh.txt"])

    response = tools.documents_rag_function("What is covered?")

    assert response == "fresh response"
    assert captured["model"] == "openai:gpt-4o-mini"
    assert captured["embeddings"] == "openai:text-embedding-3-small"
