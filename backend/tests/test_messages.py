import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from .utils import auth_header, bootstrap_admin_and_user


def _fetch_rows(query: str, params: tuple = ()):
    db_path = Path(os.environ["SIMPLECHAT_DB_PATH"])
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row  # type: ignore[attr-defined]
        return conn.execute(query, params).fetchall()


def test_text_message_and_reply_persist(client: TestClient):
    _, user, _, user_token = bootstrap_admin_and_user(client)
    resp = client.post("/api/messages", data={"content": "Hi there"}, headers=auth_header(user_token))
    assert resp.status_code == 200, resp.text

    rows = _fetch_rows("SELECT sender_type, content FROM message WHERE user_id = ? ORDER BY id", (user["id"],))
    assert len(rows) == 2  # user + simulated assistant reply
    assert rows[0]["sender_type"] == "user"
    assert rows[0]["content"] == "Hi there"
    assert rows[1]["sender_type"] == "assistant"
    assert "接收到文字訊息" in rows[1]["content"]


def test_single_file_message_persists_metadata(client: TestClient):
    _, user, _, user_token = bootstrap_admin_and_user(client)
    upload_root = Path(os.environ["CHAT_UPLOAD_ROOT"])
    files = [("files", ("hello.txt", b"Hello World", "text/plain"))]
    resp = client.post(
        "/api/messages",
        data={"content": "Hello admin!", "sender_type": "user"},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["user_id"] == user["id"]

    saved_path = upload_root / payload["files"][0]["file_path"]
    assert saved_path.exists()

    file_rows = _fetch_rows("SELECT file_name, mime_type FROM message_file WHERE message_id = ?", (payload["id"],))
    assert len(file_rows) == 1
    assert file_rows[0]["file_name"] == "hello.txt"
    assert file_rows[0]["mime_type"] == "text/plain"


def test_multiple_file_message_persists_all_metadata(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    files = [
        ("files", ("a.txt", b"A", "text/plain")),
        ("files", ("b.txt", b"B", "text/plain")),
    ]
    resp = client.post(
        "/api/messages",
        data={"content": "Upload two files"},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    stored_files = _fetch_rows("SELECT file_name FROM message_file WHERE message_id = ? ORDER BY id", (payload["id"],))
    simplified = [row["file_name"].split("_", 1)[-1] for row in stored_files]
    assert simplified == ["a.txt", "b.txt"]


def test_file_only_message_with_no_text_persists(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    files = [("files", ("img.png", b"\x89PNG", "image/png"))]
    resp = client.post(
        "/api/messages",
        data={"content": ""},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["content"] == ""
    file_rows = _fetch_rows("SELECT file_name FROM message_file WHERE message_id = ?", (payload["id"],))
    assert len(file_rows) == 1
    assert file_rows[0]["file_name"] == "img.png"


def test_user_cannot_send_assistant_message(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    resp = client.post(
        "/api/messages",
        data={"content": "Nope", "sender_type": "assistant"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403
    assert "Only admins can create assistant messages" in resp.text


def test_admin_can_send_assistant_message_without_simulated_reply(client: TestClient):
    admin, _, admin_token, _ = bootstrap_admin_and_user(client)
    resp = client.post(
        "/api/messages",
        data={"content": "System notice", "sender_type": "assistant"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["sender_type"] == "assistant"
    assert "simulated_reply" not in payload

    resp = client.get(
        "/api/messages",
        params={"user_id": admin["id"], "include_assistant": True},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    admin_messages = resp.json()
    assert len(admin_messages) == 1
    assert admin_messages[0]["sender_type"] == "assistant"


def test_invalid_sender_type_rejected(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    resp = client.post(
        "/api/messages",
        data={"content": "Weird", "sender_type": "system"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400
    assert "Invalid sender type" in resp.text
