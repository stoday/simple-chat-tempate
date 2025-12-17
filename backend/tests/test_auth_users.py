import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
  # Fresh DB and secret for every test module
  db_path = tmp_path / "test_simplechat.db"
  monkeypatch.setenv("SECRET_KEY", "testsecret")
  monkeypatch.setenv("SIMPLECHAT_DB_PATH", str(db_path))

  import backend.database as database
  import backend.main as main

  importlib.reload(database)
  importlib.reload(main)

  with TestClient(main.app) as test_client:
    yield test_client


def auth_header(token: str) -> dict:
  return {"Authorization": f"Bearer {token}"}


def test_full_user_flow(client: TestClient):
  # Register first user -> becomes admin
  resp = client.post(
    "/api/auth/register",
    json={"email": "admin@example.com", "password": "password123", "display_name": "Admin"},
  )
  assert resp.status_code == 201, resp.text
  admin_user = resp.json()
  assert admin_user["role"] == "admin"
  assert admin_user["email"] == "admin@example.com"

  # Register second user -> normal user
  resp = client.post(
    "/api/auth/register",
    json={"email": "user@example.com", "password": "password123", "display_name": "User"},
  )
  assert resp.status_code == 201, resp.text
  second_user = resp.json()
  assert second_user["role"] == "user"

  # Admin login
  resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
  assert resp.status_code == 200
  admin_token = resp.json()["access_token"]

  # User login
  resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "password123"})
  assert resp.status_code == 200
  user_token = resp.json()["access_token"]

  # /me endpoint
  resp = client.get("/api/auth/me", headers=auth_header(admin_token))
  assert resp.status_code == 200
  assert resp.json()["email"] == "admin@example.com"

  # Admin listing users
  resp = client.get("/api/users", headers=auth_header(admin_token))
  assert resp.status_code == 200
  users = resp.json()
  assert len(users) == 2

  # Non-admin cannot list users
  resp = client.get("/api/users", headers=auth_header(user_token))
  assert resp.status_code == 403

  # Normal user can see self
  resp = client.get("/api/users/2", headers=auth_header(user_token))
  assert resp.status_code == 200
  assert resp.json()["email"] == "user@example.com"

  # Normal user cannot change their role
  resp = client.patch("/api/users/2", json={"role": "admin"}, headers=auth_header(user_token))
  assert resp.status_code == 403

  # Admin updates user display name + password
  resp = client.patch(
    "/api/users/2",
    json={"display_name": "User Renamed", "password": "newpassword456"},
    headers=auth_header(admin_token),
  )
  assert resp.status_code == 200
  assert resp.json()["display_name"] == "User Renamed"

  # User logs in with new password
  resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "newpassword456"})
  assert resp.status_code == 200
  user_token = resp.json()["access_token"]

  # Admin cannot delete self
  resp = client.delete("/api/users/1", headers=auth_header(admin_token))
  assert resp.status_code == 400

  # Admin deletes second user
  resp = client.delete("/api/users/2", headers=auth_header(admin_token))
  assert resp.status_code == 200
  assert resp.json()["detail"] == "User deleted"

  # Verify deletion
  resp = client.get("/api/users/2", headers=auth_header(admin_token))
  assert resp.status_code == 404
