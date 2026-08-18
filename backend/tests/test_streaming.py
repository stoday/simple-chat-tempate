import json
import threading
import time

from fastapi.testclient import TestClient

from .test_messages import create_conversation
from .utils import (
    auth_header,
    bootstrap_admin_and_user,
    login_user,
    register_user,
)


def _parse_sse(body: str) -> list[dict]:
    events = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        if not frame.strip():
            continue
        fields = {}
        for line in frame.splitlines():
            name, _, value = line.partition(":")
            fields[name] = value.lstrip()
        events.append({"id": int(fields["id"]), "data": json.loads(fields["data"])})
    return events


def _wait_for_public_status(
    client: TestClient,
    token: str,
    conversation_id: int,
    message_id: int,
    expected: str,
    timeout: float = 3,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(
            "/api/messages",
            params={"conversation_id": conversation_id, "include_assistant": True},
            headers=auth_header(token),
        )
        messages = response.json()["messages"]
        message = next(item for item in messages if item["id"] == message_id)
        if message["status"] == expected:
            return message
        time.sleep(0.02)
    raise AssertionError(f"message {message_id} did not reach public status {expected}")


def test_agent_events_stream_with_one_versioned_contract(client: TestClient, monkeypatch):
    import backend.main as main

    class FakeAgent:
        def __call__(self, *, question: str, include_thinking: bool):
            assert question
            assert include_thinking is True
            yield {"type": "thinking", "data": "Checking records"}
            yield {
                "type": "tool",
                "data": {
                    "name": "lookup_customer",
                    "tool_call_id": "call-1",
                    "content": json.dumps(
                        {
                            "count": 2,
                            "api_key": "must-not-leak",
                            "details": "x" * 20_000,
                        }
                    ),
                },
            }
            yield {"type": "answer", "data": "Hello "}
            yield {"type": "answer", "data": "world"}

    monkeypatch.setattr(main, "get_agent", lambda stream=True: FakeAgent())
    monkeypatch.setattr(main, "_generate_conversation_title", lambda content: "Generated title")
    monkeypatch.setattr(main, "SIMULATED_REPLY_DELAY", 0)

    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "New Chat")
    created = client.post(
        "/api/messages",
        data={"content": "Stream this", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    assert created.status_code == 200, created.text
    message_id = created.json()["reply"]["id"]

    streamed = client.get(
        f"/api/messages/{message_id}/stream",
        headers=auth_header(token),
    )

    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(streamed.text)
    assert [event["id"] for event in events] == [1, 2, 3, 4, 5, 6]
    assert [event["data"]["type"] for event in events] == [
        "thinking",
        "tool_call",
        "tool_result",
        "answer_delta",
        "answer_delta",
        "done",
    ]
    assert all(event["data"]["version"] == 1 for event in events)
    assert all(event["data"]["message_id"] == message_id for event in events)
    assert events[0]["data"]["payload"] == {
        "kind": "summary",
        "text": "Checking records",
    }
    assert events[1]["data"]["payload"]["call_id"] == "call-1"
    assert events[2]["data"]["payload"]["call_id"] == "call-1"
    assert "must-not-leak" not in streamed.text
    assert "[REDACTED]" in streamed.text
    result_preview = events[2]["data"]["payload"]["result"]
    assert result_preview["truncated"] is True
    assert result_preview["original_size"] > 16_000
    assert result_preview["content_type"] == "application/json"
    assert events[3]["data"]["payload"] == {"delta": "Hello "}
    assert events[4]["data"]["payload"] == {"delta": "world"}
    assert events[5]["data"]["payload"] == {"conversation_title": "Generated title"}

    history = client.get(
        "/api/messages",
        params={"conversation_id": conversation_id, "include_assistant": True},
        headers=auth_header(token),
    )
    assistant = next(
        item for item in history.json()["messages"] if item["id"] == message_id
    )
    assert [event["type"] for event in assistant["events"]] == [
        "thinking",
        "tool_call",
        "tool_result",
        "answer_delta",
        "answer_delta",
        "done",
    ]

    replayed = client.get(
        f"/api/messages/{message_id}/stream",
        params={"after_sequence": 4},
        headers=auth_header(token),
    )
    replay_events = _parse_sse(replayed.text)
    assert [event["id"] for event in replay_events] == [5, 6]
    assert [event["data"]["type"] for event in replay_events] == ["answer_delta", "done"]


def test_stop_is_idempotent_and_replays_one_terminal_event(client: TestClient, monkeypatch):
    import backend.main as main

    monkeypatch.setattr(main, "SIMULATED_REPLY_DELAY", 30)
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Stop")
    created = client.post(
        "/api/messages",
        data={"content": "Stop this", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    message_id = created.json()["reply"]["id"]

    first = client.post(f"/api/messages/{message_id}/stop", headers=auth_header(token))
    second = client.post(f"/api/messages/{message_id}/stop", headers=auth_header(token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "stopped"
    assert second.json()["status"] == "stopped"
    assert second.json()["stopped_at"] == first.json()["stopped_at"]

    replayed = client.get(
        f"/api/messages/{message_id}/stream",
        headers=auth_header(token),
    )
    events = _parse_sse(replayed.text)
    assert [event["data"]["type"] for event in events] == ["stopped"]


def test_stop_preserves_partial_answer_and_discards_late_worker_output(
    client: TestClient, monkeypatch
):
    import backend.main as main

    release_worker = threading.Event()

    class SlowAgent:
        def __call__(self, *, question: str, include_thinking: bool):
            yield {"type": "answer", "data": "Useful partial"}
            release_worker.wait(timeout=2)
            yield {"type": "answer", "data": " must be discarded"}

    monkeypatch.setattr(main, "get_agent", lambda stream=True: SlowAgent())
    monkeypatch.setattr(main, "SIMULATED_REPLY_DELAY", 0)
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Late output")
    created = client.post(
        "/api/messages",
        data={"content": "Stop after partial", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    message_id = created.json()["reply"]["id"]

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(
            "/api/messages",
            params={"conversation_id": conversation_id, "include_assistant": True},
            headers=auth_header(token),
        )
        assistant = next(
            item for item in response.json()["messages"] if item["id"] == message_id
        )
        if assistant["content"] == "Useful partial":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("partial answer was not persisted before timeout")

    stopped = client.post(
        f"/api/messages/{message_id}/stop", headers=auth_header(token)
    )
    release_worker.set()
    time.sleep(0.1)

    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["content"] == "Useful partial"
    replayed = client.get(
        f"/api/messages/{message_id}/stream", headers=auth_header(token)
    )
    events = _parse_sse(replayed.text)
    assert [event["data"]["type"] for event in events] == [
        "answer_delta",
        "stopped",
    ]
    assert "must be discarded" not in replayed.text


def test_agent_failure_preserves_partial_answer_without_leaking_exception(
    client: TestClient, monkeypatch
):
    import backend.main as main

    class FailingAgent:
        def __call__(self, *, question: str, include_thinking: bool):
            yield {"type": "answer", "data": "Useful partial answer"}
            raise RuntimeError("provider traceback contains super-secret-value")

    monkeypatch.setattr(main, "get_agent", lambda stream=True: FailingAgent())
    monkeypatch.setattr(main, "SIMULATED_REPLY_DELAY", 0)
    _, _, _, token = bootstrap_admin_and_user(client)
    conversation_id = create_conversation(client, token, "Failure")
    created = client.post(
        "/api/messages",
        data={"content": "Fail safely", "conversation_id": str(conversation_id)},
        headers=auth_header(token),
    )
    message_id = created.json()["reply"]["id"]

    failed_message = _wait_for_public_status(
        client, token, conversation_id, message_id, "error"
    )
    assert failed_message["content"] == "Useful partial answer"

    replayed = client.get(
        f"/api/messages/{message_id}/stream",
        headers=auth_header(token),
    )
    events = _parse_sse(replayed.text)
    assert [event["data"]["type"] for event in events] == ["answer_delta", "error"]
    error_payload = events[-1]["data"]["payload"]
    assert error_payload == {
        "code": "assistant_generation_failed",
        "message": "Response generation failed.",
        "retryable": True,
        "stage": "generation",
    }
    assert "super-secret-value" not in replayed.text
    assert "Traceback" not in replayed.text


def test_stream_replay_requires_message_owner_and_events_follow_conversation_retention(
    client: TestClient, monkeypatch
):
    import backend.main as main

    monkeypatch.setattr(main, "SIMULATED_REPLY_DELAY", 30)
    _, _, _, owner_token = bootstrap_admin_and_user(client)
    register_user(client, "other@example.com", "password123", "Other")
    other_token = login_user(client, "other@example.com", "password123")
    conversation_id = create_conversation(client, owner_token, "Private stream")
    created = client.post(
        "/api/messages",
        data={"content": "Private", "conversation_id": str(conversation_id)},
        headers=auth_header(owner_token),
    )
    message_id = created.json()["reply"]["id"]
    client.post(f"/api/messages/{message_id}/stop", headers=auth_header(owner_token))

    missing_auth = client.get(f"/api/messages/{message_id}/stream")
    wrong_owner = client.get(
        f"/api/messages/{message_id}/stream", headers=auth_header(other_token)
    )
    assert missing_auth.status_code == 401
    assert wrong_owner.status_code == 403

    deleted = client.delete(
        f"/api/conversations/{conversation_id}", headers=auth_header(owner_token)
    )
    assert deleted.status_code == 200
    with main.get_connection() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM message_event WHERE message_id = ?", (message_id,)
        ).fetchone()[0]
    assert remaining == 0
