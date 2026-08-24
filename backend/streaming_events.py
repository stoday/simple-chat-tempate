import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable


STREAM_VERSION = 1
TERMINAL_EVENT_TYPES = {"done", "error", "stopped"}
MAX_PREVIEW_BYTES = 16 * 1024
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


def _is_secret_key(key: Any) -> bool:
    normalised = str(key).casefold().replace("-", "_")
    return any(part in normalised for part in _SECRET_KEY_PARTS)


def sanitise_for_browser(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _is_secret_key(key) else sanitise_for_browser(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitise_for_browser(item) for item in value]
    if isinstance(value, bytes):
        return {"content_type": "application/octet-stream", "size": len(value), "omitted": True}
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return sanitise_for_browser(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_PREVIEW_BYTES:
            preview = encoded[:MAX_PREVIEW_BYTES].decode("utf-8", errors="ignore")
            return {
                "preview": preview,
                "truncated": True,
                "original_size": len(encoded),
                "content_type": "text/plain",
            }
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def bounded_preview(value: Any) -> Any:
    safe_value = sanitise_for_browser(value)
    if isinstance(safe_value, (dict, list)):
        serialised = json.dumps(safe_value, ensure_ascii=False)
        content_type = "application/json"
    else:
        serialised = str(safe_value)
        content_type = "text/plain"
    encoded = serialised.encode("utf-8")
    if len(encoded) <= MAX_PREVIEW_BYTES:
        return safe_value
    return {
        "preview": encoded[:MAX_PREVIEW_BYTES].decode("utf-8", errors="ignore"),
        "truncated": True,
        "original_size": len(encoded),
        "content_type": content_type,
    }


def translate_agent_event(raw_event: Any, seen_tool_calls: set[str]) -> Iterable[tuple[str, dict]]:
    if isinstance(raw_event, str):
        if raw_event:
            yield "answer_delta", {"delta": raw_event}
        return
    if not isinstance(raw_event, dict):
        text = str(raw_event)
        if text:
            yield "answer_delta", {"delta": text}
        return

    event_type = raw_event.get("type")
    data = raw_event.get("data")
    if event_type == "thinking" and data:
        yield "thinking", {"kind": "summary", "text": str(data)}
    elif event_type == "answer" and data:
        yield "answer_delta", {"delta": str(data)}
    elif event_type == "tool":
        tool_data = data if isinstance(data, dict) else {"content": data}
        call_id = str(tool_data.get("tool_call_id") or tool_data.get("id") or "unknown")
        name = str(tool_data.get("name") or "tool")
        if call_id not in seen_tool_calls:
            seen_tool_calls.add(call_id)
            yield "tool_call", {
                "call_id": call_id,
                "name": name,
                "status": "started",
                "arguments": bounded_preview(tool_data.get("args") or {}),
                "result": bounded_preview(tool_data.get("content")),
            }
        yield "tool_result", {
            "call_id": call_id,
            "name": name,
            "status": tool_data.get("status") or "success",
            "result": bounded_preview(tool_data.get("content")),
        }


def append_event(conn: sqlite3.Connection, message_id: int, event_type: str, payload: dict) -> dict:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM message_event WHERE message_id = ?",
        (message_id,),
    ).fetchone()
    sequence = int(row[0])
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    safe_payload = sanitise_for_browser(payload)
    conn.execute(
        """
        INSERT INTO message_event (message_id, sequence, event_type, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message_id, sequence, event_type, json.dumps(safe_payload, ensure_ascii=False), timestamp),
    )
    return {
        "version": STREAM_VERSION,
        "type": event_type,
        "message_id": message_id,
        "sequence": sequence,
        "timestamp": timestamp,
        "payload": safe_payload,
    }


def list_events(conn: sqlite3.Connection, message_id: int, after_sequence: int = 0) -> list[dict]:
    rows = conn.execute(
        """
        SELECT message_id, sequence, event_type, payload_json, created_at
        FROM message_event
        WHERE message_id = ? AND sequence > ?
        ORDER BY sequence ASC
        """,
        (message_id, after_sequence),
    ).fetchall()
    return [
        {
            "version": STREAM_VERSION,
            "type": row["event_type"],
            "message_id": row["message_id"],
            "sequence": row["sequence"],
            "timestamp": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in rows
    ]


def encode_sse(event: dict) -> str:
    return f"id: {event['sequence']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
