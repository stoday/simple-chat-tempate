from fastapi.testclient import TestClient


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_user(client: TestClient, email: str, password: str, display_name: str) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login_user(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def bootstrap_admin_and_user(client: TestClient):
    admin = register_user(client, "admin@example.com", "password123", "Admin")
    user = register_user(client, "user@example.com", "password123", "User")
    admin_token = login_user(client, "admin@example.com", "password123")
    user_token = login_user(client, "user@example.com", "password123")
    return admin, user, admin_token, user_token
