import os
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from .utils import auth_header, bootstrap_admin_and_user


def create_conversation(client: TestClient, token: str, title: str = "Test Chat") -> int:
    resp = client.post(
        "/api/conversations",
        json={"title": title},
        headers=auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _fetch_rows(query: str, params: tuple = ()):
    db_path = Path(os.environ["SIMPLECHAT_DB_PATH"])
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row  # type: ignore[attr-defined]
        return conn.execute(query, params).fetchall()


def wait_for_status(message_id: int, expected: str, timeout: float = 3.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        rows = _fetch_rows("SELECT status FROM message WHERE id = ?", (message_id,))
        if rows and rows[0]["status"] == expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"message {message_id} did not reach status {expected}")


def test_text_message_and_reply_persist(client: TestClient):
    _, user, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token)
    resp = client.post(
        "/api/messages",
        data={"content": "Hi there", "conversation_id": str(conversation_id)},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    wait_for_status(payload["simulated_reply"]["id"], "completed")

    rows = _fetch_rows("SELECT sender_type, content FROM message WHERE user_id = ? ORDER BY id", (user["id"],))
    assert len(rows) == 2  # user + simulated assistant reply
    assert rows[0]["sender_type"] == "user"
    assert rows[0]["content"] == "Hi there"
    assert rows[1]["sender_type"] == "assistant"
    assert "Assistant received text message: Hi there" in rows[1]["content"]
    assert "Assistant did not receive any files." in rows[1]["content"]


def test_single_file_message_persists_metadata(client: TestClient):
    _, user, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token, "Files")
    upload_root = Path(os.environ["CHAT_UPLOAD_ROOT"])
    files = [("files", ("hello.txt", b"Hello World", "text/plain"))]
    resp = client.post(
        "/api/messages",
        data={"content": "Hello admin!", "sender_type": "user", "conversation_id": str(conversation_id)},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()["message"]
    assert payload["user_id"] == user["id"]

    saved_path = upload_root / payload["files"][0]["file_path"]
    assert saved_path.exists()

    file_rows = _fetch_rows("SELECT file_name, mime_type FROM message_file WHERE message_id = ?", (payload["id"],))
    assert len(file_rows) == 1
    assert file_rows[0]["file_name"] == "hello.txt"
    assert file_rows[0]["mime_type"] == "text/plain"


def test_multiple_file_message_persists_all_metadata(client: TestClient):
    _, user, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token, "Multi")
    files = [
        ("files", ("a.txt", b"A", "text/plain")),
        ("files", ("b.txt", b"B", "text/plain")),
    ]
    resp = client.post(
        "/api/messages",
        data={"content": "Upload two files", "conversation_id": str(conversation_id)},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()["message"]
    stored_files = _fetch_rows("SELECT file_name FROM message_file WHERE message_id = ? ORDER BY id", (payload["id"],))
    simplified = [row["file_name"].split("_", 1)[-1] for row in stored_files]
    assert simplified == ["a.txt", "b.txt"]


def test_message_listing_for_user_and_admin(client: TestClient):
    _, user, admin_token, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token, "Review")
    files = [("files", ("doc.txt", b"Review", "text/plain"))]
    resp = client.post(
        "/api/messages",
        data={"conversation_id": str(conversation_id), "content": "Review doc"},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    wait_for_status(resp.json()["simulated_reply"]["id"], "completed")

    resp = client.get(
        "/api/messages",
        params={"conversation_id": conversation_id},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    user_messages = resp.json()
    assert len(user_messages) == 1
    assert user_messages[0]["sender_type"] == "user"

    resp = client.get(
        "/api/messages",
        params={"user_id": user["id"], "conversation_id": conversation_id, "include_assistant": True},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    admin_messages = resp.json()
    assert len(admin_messages) == 2
    assert any(msg["sender_type"] == "assistant" for msg in admin_messages)


def test_file_only_message_with_no_text_persists(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token, "File only")
    files = [("files", ("img.png", b"\x89PNG", "image/png"))]
    resp = client.post(
        "/api/messages",
        data={"content": "", "conversation_id": str(conversation_id)},
        files=files,
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()["message"]
    assert payload["content"] == ""
    file_rows = _fetch_rows("SELECT file_name FROM message_file WHERE message_id = ?", (payload["id"],))
    assert len(file_rows) == 1
    assert file_rows[0]["file_name"] == "img.png"


def test_user_cannot_send_assistant_message(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token)
    resp = client.post(
        "/api/messages",
        data={"content": "Nope", "sender_type": "assistant", "conversation_id": str(conversation_id)},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403
    assert "Only admins can create assistant messages" in resp.text


def test_admin_can_send_assistant_message_without_simulated_reply(client: TestClient):
    admin, _, admin_token, _ = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, admin_token)
    resp = client.post(
        "/api/messages",
        data={"content": "System notice", "sender_type": "assistant", "conversation_id": str(conversation_id)},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["simulated_reply"] is None
    message_payload = payload["message"]
    assert message_payload["sender_type"] == "assistant"

    resp = client.get(
        "/api/messages",
        params={"user_id": admin["id"], "conversation_id": conversation_id, "include_assistant": True},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    admin_messages = resp.json()
    assert len(admin_messages) == 1
    assert admin_messages[0]["sender_type"] == "assistant"


def test_invalid_sender_type_rejected(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token)
    resp = client.post(
        "/api/messages",
        data={"content": "Weird", "sender_type": "system", "conversation_id": str(conversation_id)},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400
    assert "Invalid sender type" in resp.text


def test_user_can_stop_pending_reply(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, user_token)
    resp = client.post(
        "/api/messages",
        data={"content": "Please stop me", "conversation_id": str(conversation_id)},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assistant_id = resp.json()["simulated_reply"]["id"]

    stop_resp = client.post(
        f"/api/messages/{assistant_id}/stop",
        headers=auth_header(user_token),
    )
    assert stop_resp.status_code == 200
    stopped_payload = stop_resp.json()
    assert stopped_payload["status"] == "cancelled"
    assert stopped_payload["stopped_at"] is not None

    rows = _fetch_rows("SELECT status FROM message WHERE id = ?", (assistant_id,))
    assert rows[0]["status"] == "cancelled"


def test_messages_remain_isolated_between_conversations(client: TestClient):
    _, _, _, user_token = bootstrap_admin_and_user(client)
    conv_a = create_conversation(client, user_token, "Chat A")
    conv_b = create_conversation(client, user_token, "Chat B")

    resp = client.post(
        "/api/messages",
        data={"content": "Message for A", "conversation_id": str(conv_a)},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    wait_for_status(resp.json()["simulated_reply"]["id"], "completed")

    resp = client.post(
        "/api/messages",
        data={"content": "Message for B", "conversation_id": str(conv_b)},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    wait_for_status(resp.json()["simulated_reply"]["id"], "completed")

    resp_a = client.get(
        "/api/messages",
        params={"conversation_id": conv_a, "include_assistant": True},
        headers=auth_header(user_token),
    )
    resp_b = client.get(
        "/api/messages",
        params={"conversation_id": conv_b, "include_assistant": True},
        headers=auth_header(user_token),
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    msgs_a = resp_a.json()
    msgs_b = resp_b.json()

    assert len(msgs_a) == 2  # user + simulated reply
    assert len(msgs_b) == 2
    assert msgs_a[0]["content"] == "Message for A"
    assert msgs_b[0]["content"] == "Message for B"
