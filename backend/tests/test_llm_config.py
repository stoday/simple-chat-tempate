from fastapi.testclient import TestClient

from .utils import auth_header, login_user, register_user


def test_admin_can_configure_embedding_model(client: TestClient):
    register_user(client, "admin@example.com", "password123", "Admin")
    token = login_user(client, "admin@example.com", "password123")
    headers = auth_header(token)

    initial = client.get("/api/admin/llm-config", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["embedding_model"] == "gemini:gemini-embedding-001"

    updated = client.patch(
        "/api/admin/llm-config",
        json={"embedding_model": "openai:text-embedding-3-small"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["embedding_model"] == "openai:text-embedding-3-small"

    persisted = client.get("/api/admin/llm-config", headers=headers)
    assert persisted.json()["embedding_model"] == "openai:text-embedding-3-small"


def test_admin_can_test_configured_llm_model(client: TestClient, monkeypatch):
    import backend.main as main

    register_user(client, "admin@example.com", "password123", "Admin")
    token = login_user(client, "admin@example.com", "password123")
    headers = auth_header(token)

    class FakeModel:
        pass

    seen = {}

    def fake_handle_model(model_name, **kwargs):
        seen["model_name"] = model_name
        return FakeModel()

    def fake_call_model(model, prompt, **kwargs):
        seen["prompt"] = prompt
        return "測試成功"

    monkeypatch.setattr(main, "handle_model", fake_handle_model)
    monkeypatch.setattr(main, "call_model", fake_call_model)

    response = client.post(
        "/api/admin/llm-config/test",
        json={"model_name": "openai:gpt-test"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": "LLM model test succeeded."}
    assert seen == {"model_name": "openai:gpt-test", "prompt": "測試"}


def test_admin_can_test_configured_embedding_model(client: TestClient, monkeypatch):
    import backend.main as main

    register_user(client, "admin@example.com", "password123", "Admin")
    token = login_user(client, "admin@example.com", "password123")
    headers = auth_header(token)

    class FakeEmbeddings:
        def embed_query(self, prompt):
            assert prompt == "測試"
            return [0.1, 0.2, 0.3]

    seen = {}

    def fake_handle_embeddings(model_name, **kwargs):
        seen["model_name"] = model_name
        return FakeEmbeddings()

    monkeypatch.setattr(main, "handle_embeddings", fake_handle_embeddings)

    response = client.post(
        "/api/admin/embedding-config/test",
        json={"embedding_model": "openai:text-embedding-test"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": "Embedding model test succeeded."}
    assert seen == {"model_name": "openai:text-embedding-test"}


def test_model_test_reports_provider_failure(client: TestClient, monkeypatch):
    import backend.main as main

    register_user(client, "admin@example.com", "password123", "Admin")
    token = login_user(client, "admin@example.com", "password123")
    headers = auth_header(token)

    def fail_handle_model(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main, "handle_model", fail_handle_model)

    response = client.post(
        "/api/admin/llm-config/test",
        json={"model_name": "openai:gpt-test"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "provider unavailable" in response.json()["detail"]
