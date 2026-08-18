# Agent streaming implementation

Status: implemented on 2026-08-18. The normative product contract and acceptance criteria are in [AGENT_STREAMING_SPEC.md](AGENT_STREAMING_SPEC.md).

## Public HTTP contract

Creating a user message with `POST /api/messages` immediately returns the persisted user message and a pending assistant message. The browser then opens:

```http
GET /api/messages/{assistant_message_id}/stream?after_sequence=0
Authorization: Bearer <access token>
Accept: text/event-stream
```

Authentication is header-only. Tokens are never accepted in the query string. Every SSE frame contains one JSON envelope and an SSE `id` equal to the event sequence:

```text
id: 4
data: {"version":1,"type":"answer_delta","message_id":42,"sequence":4,"timestamp":"2026-08-18T03:00:00.000Z","payload":{"delta":"partial text"}}

```

The only event types are:

| Type | Payload purpose |
| --- | --- |
| `thinking` | Public stage or reasoning summary, never hidden chain-of-thought |
| `tool_call` | Sanitised tool name, call id, state, and bounded argument preview |
| `tool_result` | Sanitised and bounded result preview correlated by call id |
| `answer_delta` | Text to append to the visible assistant answer |
| `done` | Successful terminal event; may include `payload.conversation_title` so the sidebar updates immediately |
| `stopped` | User-requested terminal event |
| `error` | Safe terminal error code/message; no traceback or provider secret |

The old `{token}` / `[DONE]` format is intentionally unsupported. The client rejects unknown protocol versions and sequence gaps, then reconnects using its last successfully applied sequence. Duplicate sequences are ignored.

## Persistence and replay

Safe browser events are sanitised before they are stored in SQLite `message_event`:

| Column | Contract |
| --- | --- |
| `message_id` | Owning assistant message; cascades on message deletion |
| `sequence` | Strictly increasing per message and unique with `message_id` |
| `event_type` | One of the version 1 event types |
| `payload_json` | Redacted, size-bounded browser payload |
| `created_at` | UTC event timestamp used in the public envelope |

`GET /api/messages` includes each message's persisted `events`. This lets the frontend restore execution details and resume a pending stream from `lastSequence` without appending persisted answer text twice. The stream endpoint replays only rows where `sequence > after_sequence`, then follows live events if the message is still pending.

Sensitive key names, including credentials, cookies, passwords, secrets, authorisation values, and tokens, are replaced with `[REDACTED]`. Tool previews are limited to approximately 16 KiB and report truncation metadata.

## Stop and terminal rules

`POST /api/messages/{assistant_message_id}/stop` is authenticated, authorised, and idempotent. The first call changes a pending message to `stopped`, preserves its partial `content`, records `stopped_at`, persists exactly one `stopped` event, and notifies live subscribers. Repeated calls return the same stopped message.

`done`, `stopped`, and `error` are mutually exclusive. Database status checks prevent late worker output from overwriting a terminal message. Python worker threads cannot be forcibly killed; stopping is immediate at the product boundary and late results are discarded.

## Frontend behaviour

The frontend consumes SSE with `fetch`, so it can send the bearer header and an `AbortSignal`. Answer deltas render immediately. Public thinking is shown as a short status. Tool calls and results are stored on the message and rendered in collapsed execution details. Error and stopped states keep any partial answer visible.

The stream reconnects up to three times with exponential backoff. A clean EOF without a terminal event is treated as an interruption and resumes after the last sequence. Clicking Stop waits for the stop API to succeed and then aborts the browser stream.

## Deployment boundary

This version requires exactly one backend Uvicorn application worker and one backend replica because live subscribers are process-local. The checked-in Docker, Compose, and Windows launch commands satisfy this constraint. Do not add `--workers`, Gunicorn multi-worker mode, or horizontal backend replicas without first moving live stream routing to a shared broker or adding verified connection affinity.

Nginx buffering and caching are disabled for `/api/` so SSE frames flush incrementally. The application also sends `X-Accel-Buffering: no`.

## Verification commands

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'C:\Users\today\Projects\Envs\P2026_HERANCHAT\.venv\Scripts\python.exe' -m pytest backend/tests -q -p no:cacheprovider
npm test
npm run build
```

Backend tests use a deterministic fake Agent at the external Agent boundary. They cover event shape and ordering, replay, redaction, preview truncation, stop idempotency, safe errors, authentication/authorisation, database cascade retention, and fresh-database startup order. Frontend tests cover chunk parsing, reducer ordering and de-duplication, persisted history hydration, reconnect, stop/abort behaviour, and message rendering. These mocks are not evidence of a successful live-provider run.
