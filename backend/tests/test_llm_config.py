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
