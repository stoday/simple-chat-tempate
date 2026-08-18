import os
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from .utils import auth_header, bootstrap_admin_and_user


def create_conversation(client: TestClient, token: str, title: str = "Test Chat") -> int:
    response = client.post(
        "/api/conversations", json={"title": title}, headers=auth_header(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _fetch_rows(query: str, params: tuple = ()):
    db_path = Path(os.environ["SIMPLECHAT_DB_PATH"])
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(query, params).fetchall()


def wait_for_status(message_id: int, expected: str, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = _fetch_rows("SELECT status FROM message WHERE id = ?", (message_id,))
        if rows and rows[0]["status"] == expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"message {message_id} did not reach status {expected}")


def test_text_message_and_reply_persist(client: TestClient):
    _, user, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token)
    response = client.post(
        "/api/messages",
        data={"content": "Hi there", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    wait_for_status(response.json()["reply"]["id"], "completed")

    rows = _fetch_rows(
        "SELECT sender_type, content FROM message WHERE user_id = ? ORDER BY id",
        (user["id"],),
    )
    assert len(rows) == 2
    assert rows[0]["sender_type"] == "user"
    assert rows[0]["content"] == "Hi there"
    assert rows[1]["sender_type"] == "assistant"
    assert rows[1]["content"].startswith("Test response:")
    assert "Hi there" in rows[1]["content"]


def test_single_file_message_persists_metadata(client: TestClient):
    _, user, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Files")
    upload_root = Path(os.environ["CHAT_UPLOAD_ROOT"])
    response = client.post(
        "/api/messages",
        data={"content": "Hello admin!", "conversation_id": str(conversation_id)},
        files=[("files", ("hello.txt", b"Hello World", "text/plain"))],
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    payload = response.json()["message"]
    assert payload["user_id"] == user["id"]
    assert (upload_root / payload["files"][0]["file_path"]).exists()
    rows = _fetch_rows(
        "SELECT file_name, mime_type FROM message_file WHERE message_id = ?",
        (payload["id"],),
    )
    assert [(row["file_name"], row["mime_type"]) for row in rows] == [
        ("hello.txt", "text/plain")
    ]


def test_multiple_file_message_persists_all_metadata(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Multi")
    response = client.post(
        "/api/messages",
        data={"content": "Upload two files", "conversation_id": str(conversation_id)},
        files=[
            ("files", ("a.txt", b"A", "text/plain")),
            ("files", ("b.txt", b"B", "text/plain")),
        ],
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    rows = _fetch_rows(
        "SELECT file_name FROM message_file WHERE message_id = ? ORDER BY id",
        (response.json()["message"]["id"],),
    )
    assert [row["file_name"] for row in rows] == ["a.txt", "b.txt"]


def test_message_listing_for_user_and_admin(client: TestClient):
    _, user, admin_token, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Review")
    created = client.post(
        "/api/messages",
        data={"conversation_id": str(conversation_id), "content": "Review doc"},
        files=[("files", ("doc.txt", b"Review", "text/plain"))],
        headers=auth_header(token),
    )
    assert created.status_code == 200, created.text
    wait_for_status(created.json()["reply"]["id"], "completed")

    user_response = client.get(
        "/api/messages",
        params={"conversation_id": conversation_id},
        headers=auth_header(token),
    )
    assert user_response.status_code == 200
    assert user_response.json()["conversation_title"] == "Review"
    assert [item["sender_type"] for item in user_response.json()["messages"]] == ["user"]

    admin_response = client.get(
        "/api/messages",
        params={"user_id": user["id"], "conversation_id": conversation_id, "include_assistant": True},
        headers=auth_header(admin_token),
    )
    assert admin_response.status_code == 200
    assert [item["sender_type"] for item in admin_response.json()["messages"]] == ["user", "assistant"]


def test_assistant_reply_is_returned_by_message_listing(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Assistant reply")
    created = client.post(
        "/api/messages",
        data={"content": "Generate a reply", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    assert created.status_code == 200, created.text
    wait_for_status(created.json()["reply"]["id"], "completed")
    response = client.get(
        "/api/messages",
        params={"conversation_id": conversation_id, "include_assistant": True},
        headers=auth_header(token),
    )
    assistant = next(item for item in response.json()["messages"] if item["sender_type"] == "assistant")
    assert assistant["content"].startswith("Test response:")
    assert assistant["files"] == []


def test_file_only_message_with_no_text_persists(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "File only")
    response = client.post(
        "/api/messages",
        data={"content": "", "conversation_id": str(conversation_id)},
        files=[("files", ("notes.txt", b"file only", "text/plain"))],
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    payload = response.json()["message"]
    assert payload["content"] == ""
    rows = _fetch_rows("SELECT file_name FROM message_file WHERE message_id = ?", (payload["id"],))
    assert [row["file_name"] for row in rows] == ["notes.txt"]


def test_user_cannot_send_assistant_message(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token)
    response = client.post(
        "/api/messages",
        data={"content": "Nope", "sender_type": "assistant", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    assert response.status_code == 403
    assert "Only admins can create assistant messages" in response.text


def test_admin_can_send_assistant_message_without_reply(client: TestClient):
    admin, _, admin_token, _ = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, admin_token)
    response = client.post(
        "/api/messages",
        data={"content": "System notice", "sender_type": "assistant", "conversation_id": str(conversation_id)},
        headers=auth_header(admin_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"] is None
    listing = client.get(
        "/api/messages",
        params={"user_id": admin["id"], "conversation_id": conversation_id, "include_assistant": True},
        headers=auth_header(admin_token),
    )
    assert [item["sender_type"] for item in listing.json()["messages"]] == ["assistant"]


def test_invalid_sender_type_rejected(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token)
    response = client.post(
        "/api/messages",
        data={"content": "Weird", "sender_type": "system", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    assert response.status_code == 400
    assert "Invalid sender type" in response.text


def test_user_can_stop_pending_reply(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token)
    created = client.post(
        "/api/messages",
        data={"content": "Please stop me", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    assistant_id = created.json()["reply"]["id"]
    stopped = client.post(f"/api/messages/{assistant_id}/stop", headers=auth_header(token))
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["stopped_at"] is not None
    assert _fetch_rows("SELECT status FROM message WHERE id = ?", (assistant_id,))[0]["status"] == "stopped"


def test_messages_remain_isolated_between_conversations(client: TestClient):
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_a = create_conversation(client, token, "Chat A")
    conversation_b = create_conversation(client, token, "Chat B")
    for conversation_id, content in ((conversation_a, "Message for A"), (conversation_b, "Message for B")):
        created = client.post(
            "/api/messages",
            data={"content": content, "conversation_id": str(conversation_id)},
            headers=auth_header(token),
        )
        assert created.status_code == 200
        wait_for_status(created.json()["reply"]["id"], "completed")

    def list_for(conversation_id: int) -> list[dict]:
        response = client.get(
            "/api/messages",
            params={"conversation_id": conversation_id, "include_assistant": True},
            headers=auth_header(token),
        )
        assert response.status_code == 200
        return response.json()["messages"]

    messages_a = list_for(conversation_a)
    messages_b = list_for(conversation_b)
    assert len(messages_a) == 2
    assert len(messages_b) == 2
    assert messages_a[0]["content"] == "Message for A"
    assert messages_b[0]["content"] == "Message for B"
