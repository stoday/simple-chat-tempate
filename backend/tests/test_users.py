from fastapi.testclient import TestClient

from .utils import auth_header, bootstrap_admin_and_user, login_user, register_user


def test_user_registration_roles(client: TestClient):
    admin = register_user(client, "admin@example.com", "password123", "Admin")
    user = register_user(client, "user@example.com", "password123", "User")
    assert admin["role"] == "admin"
    assert user["role"] == "user"


def test_user_login_and_me_endpoint(client: TestClient):
    register_user(client, "admin@example.com", "password123", "Admin")
    login_user(client, "admin@example.com", "password123")
    token = login_user(client, "admin@example.com", "password123")
    resp = client.get("/api/auth/me", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@example.com"


def test_user_permissions_for_listing(client: TestClient):
    _, _, admin_token, user_token = bootstrap_admin_and_user(client)

    resp = client.get("/api/users", headers=auth_header(admin_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = client.get("/api/users", headers=auth_header(user_token))
    assert resp.status_code == 403


def test_user_self_access_and_role_change_limit(client: TestClient):
    _, user, _, user_token = bootstrap_admin_and_user(client)

    resp = client.get(f"/api/users/{user['id']}", headers=auth_header(user_token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@example.com"

    resp = client.patch(
        f"/api/users/{user['id']}",
        json={"role": "admin"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403


def test_user_update_and_password_reset_flow(client: TestClient):
    _, user, admin_token, _ = bootstrap_admin_and_user(client)

    resp = client.patch(
        f"/api/users/{user['id']}",
        json={"display_name": "User Renamed", "password": "newpassword456"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "User Renamed"

    new_token = login_user(client, "user@example.com", "newpassword456")
    assert new_token


def test_user_deletion_flow(client: TestClient):
    _, user, admin_token, _ = bootstrap_admin_and_user(client)

    resp = client.delete("/api/users/1", headers=auth_header(admin_token))
    assert resp.status_code == 400

    resp = client.delete(f"/api/users/{user['id']}", headers=auth_header(admin_token))
    assert resp.status_code == 200
    assert resp.json()["detail"] == "User deleted"

    resp = client.get(f"/api/users/{user['id']}", headers=auth_header(admin_token))
    assert resp.status_code == 404
