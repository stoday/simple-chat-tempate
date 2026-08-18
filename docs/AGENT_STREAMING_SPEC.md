# Agent 前後端串流實作契約

狀態：Ready for implementation  
日期：2026-08-18

## Problem Statement

目前聊天介面雖然已能以 SSE 逐段接收 Agent 回答，也提供停止按鈕，但串流協定只包含文字 token、錯誤與完成標記。Agent 的執行階段、工具呼叫及工具結果沒有結構化事件，因此前端無法可靠地選擇哪些資訊要顯示。

現有串流亦缺少協定層測試、斷線重播、安全清理及明確的終止狀態規則。停止操作只會停止等待與前端串流，執行中的 Agent 執行緒可能繼續產生遲到結果。清理流程另有未定義變數問題，可能阻止 pending generation 與 stream 資源釋放。若只修改畫面而沒有建立後端契約，前端仍可能因事件格式、順序或終止競態而呈現錯誤狀態。

## Solution

建立一套前後端同步更新、沒有舊格式相容層的版本化 SSE 事件協定。後端以結構化事件傳送可公開的思考階段或 reasoning summary、工具呼叫、安全化的工具結果、回答增量，以及唯一的終止事件。前端使用帶有 Bearer authentication 的 `fetch` 串流消費 SSE，讓回答文字逐段顯示，將思考階段呈現為簡短狀態，並將工具活動放在預設收合的執行詳情中。

所有允許送到瀏覽器的事件都先在後端遮罩及截斷，再持久化到訊息事件紀錄。每個事件具有遞增序號，使重新整理或短暫斷線後能從最後序號重播，而不會重新執行 Agent。停止生成在產品邊界上必須立即生效：停止推送、保存部分回答、標記訊息為 stopped，並忽略底層執行緒的任何遲到結果。

## User Stories

1. As a chat user, I want the assistant answer to appear in chunks, so that I can begin reading before generation finishes.
2. As a chat user, I want to see a short description of the Agent's current stage, so that I know whether it is analysing, using a tool, or composing an answer.
3. As a chat user, I want tool activity grouped under an execution-details control, so that the main conversation remains readable.
4. As a chat user, I want execution details collapsed by default, so that implementation details do not distract from the answer.
5. As a chat user, I want to expand a tool call and see its safe input summary and result summary, so that I can understand how the answer was produced.
6. As a chat user, I want the stop button to take effect immediately, so that I do not continue receiving unwanted output.
7. As a chat user, I want the partial answer to remain visible after stopping, so that useful content is not discarded.
8. As a chat user, I want a stopped response to be visibly marked as incomplete, so that I do not mistake it for a complete answer.
9. As a chat user, I want repeated stop actions to be harmless, so that double-clicks or retries do not produce an error.
10. As a chat user, I want a safe and understandable error message when generation fails, so that I know whether retrying may help.
11. As a chat user, I want partial content to remain visible after an error, so that work completed before the failure is preserved.
12. As a chat user, I want a short network interruption to reconnect automatically, so that generation can continue without manual recovery.
13. As a chat user, I want reconnecting to resume after my last received event, so that content and tool activity are not duplicated.
14. As a chat user, I want refreshing the page to restore the safe execution history, so that I can continue following a pending response.
15. As a chat user, I want reopening an old conversation to restore its execution details, so that the prior answer remains auditable.
16. As a security-conscious user, I want credentials and sensitive tool data removed before events reach my browser, so that hiding a panel is not treated as a security boundary.
17. As an administrator, I want users to access only events belonging to conversations they are authorised to view, so that event replay cannot bypass message permissions.
18. As an administrator, I want full internal exceptions retained only in server logs, so that browser clients do not receive tracebacks or server internals.
19. As a developer, I want one versioned event envelope for every event type, so that frontend handling and backend tests share a stable contract.
20. As a developer, I want each event to carry a per-message sequence number, so that ordering, replay, gaps, and duplicates can be handled deterministically.
21. As a developer, I want exactly one terminal event per Agent run, so that completion, stopping, and failure cannot conflict.
22. As a developer, I want events after a terminal state to be rejected or ignored, so that late Agent output cannot overwrite the final state.
23. As a developer, I want deterministic mocked streams in automated tests, so that the full contract can be verified without provider credentials.
24. As a developer, I want a browser smoke flow in addition to unit tests, so that buffering and reactive rendering failures are caught at the integration boundary.
25. As an operator, I want the deployment limitation of one backend worker documented, so that an unsupported multi-worker configuration is not mistaken for safe operation.
26. As a maintainer, I want event records deleted with their conversation messages, so that retention follows the existing conversation lifecycle.

## Implementation Decisions

### Transport and authentication

- Retain Server-Sent Events as the server-to-browser protocol. WebSocket is not required because this feature needs one-way event delivery; stopping remains a separate authenticated HTTP command.
- Replace native `EventSource` consumption with `fetch` streaming. The stream request uses the existing Bearer authentication header rather than putting an access token in the URL.
- The client owns an `AbortController` for each active stream. Aborting a client connection and requesting Agent stop are distinct actions: the stop action first sends the authenticated stop request, then closes the local stream.
- The stream response remains `text/event-stream`, disables caching, and must be verified to flush incrementally through the configured reverse proxy.
- Frontend and backend switch to the new contract together. The old `{token}`, `{error}`, and `[DONE]` payload forms are removed without a compatibility mode.

### Event envelope

- Every SSE frame contains an `id` equal to its per-message sequence number and a JSON `data` object with these required top-level fields:
  - `version`: integer protocol version, initially `1`.
  - `type`: one of `thinking`, `tool_call`, `tool_result`, `answer_delta`, `error`, `done`, or `stopped`.
  - `message_id`: the assistant message identifier as a string or number in one consistent representation.
  - `sequence`: a positive integer that increases monotonically within one assistant message.
  - `timestamp`: a UTC ISO 8601 timestamp.
  - `payload`: an object whose schema is determined by `type`.
- Sequence numbers are unique per assistant message. The backend is the only authority that assigns them.
- The client processes an event at most once. An event whose sequence is not greater than the last applied sequence is ignored. A detected gap initiates recovery rather than silently applying later events.
- Event ordering follows observable execution ordering. A tool result references an earlier tool call, and no non-terminal event may follow a terminal event.

### Event payloads

- `thinking` contains `kind` (`stage` or `summary`) and public `text`. It may contain a stable stage code for frontend presentation. It never contains hidden chain-of-thought or raw internal reasoning.
- `tool_call` contains a stable `call_id`, tool `name`, execution status, and sanitised argument preview.
- `tool_result` contains the matching `call_id`, tool `name`, success or failure status, sanitised result preview, content type, truncation metadata, and an optional safe error summary.
- `answer_delta` contains only the next answer text fragment. Appending deltas in sequence produces the visible partial or final answer.
- `error` contains a stable error `code`, user-safe `message`, `retryable` boolean, and failure `stage`. It contains no traceback.
- `done` marks successful completion and may include final usage or timing metadata that is already safe for the authenticated user.
- `stopped` contains a safe reason and stop timestamp. It marks the accumulated answer as intentionally incomplete.

### Information safety

- The backend sanitises event data before both transmission and persistence. The frontend display choice is not a security control.
- Known secret-bearing keys, including credentials, tokens, passwords, cookies, authorisation values, and API keys, are recursively redacted without case sensitivity.
- Tool arguments and tool results each have a maximum serialised preview size of approximately 16 KiB. Oversized values are truncated and include `truncated: true`, original size when known, and content type.
- Binary data, complete uploaded-file bodies, complete retrieved documents, environment variables, internal filesystem details, and raw exception objects are not emitted. They are represented by safe metadata or a short summary when useful.
- Sanitisation failure fails closed: emit a safe error or omit the preview rather than sending raw data.
- Full tracebacks and unredacted internal diagnostics remain in protected backend logs only.

### Persistence and replay

- Add a message-event persistence model associated with an assistant message. It stores sequence, event type, sanitised payload JSON, and creation timestamp, with a uniqueness constraint on message plus sequence.
- Event rows have the same lifecycle as their assistant message and are cascade-deleted when the message or conversation is deleted.
- Only the already-sanitised browser-safe envelope is persisted. Raw reasoning, raw tool payloads, and tracebacks are never written to this event store.
- The persisted event log is the replay source of truth. The current process-local notification mechanism may wake connected clients, but must not be the only copy of an event.
- A reconnect request supplies `after_sequence`. The server replays all authorised persisted events with a greater sequence, in order, and then waits for new events when the run remains active.
- The replay-to-live handoff must have no gap. It may safely deliver a duplicate because the client reducer is sequence-idempotent, but it must not omit an event produced during handoff.
- Reloading a completed, stopped, or failed message replays its stored timeline and terminal event without starting a new Agent run.
- Partial answer content is recoverable from persisted `answer_delta` events after refresh, stop, error, or process interruption.

### Stream and message state machine

- A generated assistant message begins in `pending`, moves to an active generation state when work starts, and ends in exactly one of `completed`, `stopped`, or `error`.
- `done`, `stopped`, and `error` are mutually exclusive terminal events. The first terminal transition committed by the backend wins.
- Once a terminal transition is committed, later deltas, thinking events, tool events, and competing terminal signals are discarded.
- Successful completion persists the concatenated answer and commits `done`.
- User stop immediately commits `stopped`, preserves the accumulated answer, notifies connected streams, and ignores any later worker output.
- Failure preserves the accumulated answer, records a safe `error` event, marks the message as failed, and logs the internal exception separately.
- The stop endpoint is idempotent. Repeating stop for an already stopped message returns the same effective outcome. Stopping an already completed or failed message does not change its terminal state.
- The implementation should request cooperative cancellation from the underlying Agent or provider when available. Hard termination of an Agent thread or arbitrary tool subprocess is not promised by this specification.
- The existing cleanup defect involving an undefined process reference is fixed, and cleanup of pending-generation and live-stream bookkeeping occurs even after stop, error, disconnect, or cancellation.

### Frontend behaviour

- The visible assistant answer appends `answer_delta` content as events arrive; it does not wait for completion.
- Public thinking events render as a short, changing execution-status area. They are visually distinct from the assistant answer.
- Tool calls and results are grouped in an execution-details panel that is collapsed by default and can be expanded by the user.
- Tool calls and results correlate by `call_id`, retain event order, and show pending, success, or failure state.
- Stopped and failed responses retain their partial answers and show a visible incomplete or error state.
- The frontend stream parser handles arbitrary network chunk boundaries: one network chunk may contain part of an SSE frame, one frame, or multiple frames.
- Stream state is scoped to the assistant message and conversation. Switching conversations must not append events to the currently visible but unrelated message.
- Automatic reconnect uses bounded exponential backoff and resumes from the last applied sequence. Explicit user stop disables reconnect for that message.
- When replay completes at a terminal event, the client closes the connection and reconciles the stored message state once.

### Deployment boundary and documentation

- This implementation supports the repository's current deployment topology: one backend application worker and one backend container, with an internal thread pool for Agent work.
- Multi-worker or multi-replica deployment is unsupported until a shared event broker or equivalent routing guarantee is added. Documentation must not recommend enabling multiple workers without explaining this requirement.
- Reverse-proxy configuration and a browser smoke test must confirm that SSE frames are flushed progressively rather than buffered until completion.
- Existing documentation is updated to describe the completed streaming flow, event persistence, stop semantics, authentication, and the single-worker limitation.

## Testing Decisions

### Test seams

- The primary backend seam is the authenticated HTTP message and SSE API exercised with a deterministic fake Agent event source. Tests assert externally observable frames, persistence, message state, and authorisation rather than private queue implementation.
- The primary frontend seam is the chat store's stream consumer and event reducer exercised with a mocked `fetch` response whose `ReadableStream` uses controlled byte boundaries.
- The presentation seam is the chat message component supplied with message state and execution events. Tests assert visible answer text, collapsed details, tool correlation, stop state, and error state.
- The highest integration seam is a local browser flow against the application with deterministic Agent output. It verifies actual incremental paint, proxy flushing, stop interaction, refresh, and replay.

### Backend contract coverage

- Assert the exact required envelope fields, protocol version, allowed event types, UTC timestamp form, SSE ids, JSON validity, and content type.
- Assert monotonic unique sequences and execution ordering across thinking, tool call, tool result, answer deltas, and one terminal event.
- Assert a complete successful run produces the correct concatenated persisted answer and `completed` state.
- Assert stop is idempotent, preserves partial output, produces one `stopped` event, closes the stream, and rejects late worker output.
- Assert completion-versus-stop and error-versus-stop races produce exactly one winning terminal state.
- Assert safe errors contain no traceback and preserve partial output.
- Assert secret keys are recursively redacted, oversized tool previews are truncated with metadata, binary or unsafe content is omitted, and sanitisation failures fail closed.
- Assert reconnect with `after_sequence` replays only later events in order and transitions to live delivery without gaps.
- Assert completed, stopped, and failed event histories replay without re-running the Agent.
- Assert event and stream access follows the same conversation ownership and administrator rules as messages.
- Assert missing, invalid, or unauthorised Bearer authentication is rejected without leaking event existence or content.
- Assert deleting a message or conversation deletes associated events.
- Assert disconnect, exception, stop, and normal completion always release pending-generation and stream bookkeeping, covering the undefined-process cleanup regression.
- Repair any existing message-contract tests that still expect a response shape different from the current messages-plus-conversation-title contract.

### Frontend coverage

- Add a Vue-compatible unit test runner and component utilities integrated with the existing Vite build.
- Assert the parser handles CRLF and LF framing, UTF-8 text, partial frames, multiple frames per network chunk, and a final frame without corrupting data.
- Assert `answer_delta` events append exactly once and duplicate sequences are ignored.
- Assert sequence gaps trigger recovery instead of silently losing content.
- Assert thinking, tool call, and tool result events update the correct message and correlate by call id.
- Assert execution details are collapsed by default and expandable, while answer text remains directly visible.
- Assert stop sends one effective stop operation, aborts the local stream, disables reconnect, and retains partial content.
- Assert network interruption reconnects after the last applied sequence and does not restart the Agent.
- Assert error, done, and stopped events terminate the stream and that later events do not alter state.
- Assert changing conversations prevents cross-conversation event updates.

### Verification levels

- Run focused backend tests for messages, streaming, persistence, stop, replay, authorisation, and cleanup.
- Run the complete backend test suite and distinguish pre-existing failures from regressions introduced by this feature.
- Run frontend unit and component tests plus the production build.
- Run a local browser smoke test through the configured reverse proxy, including progressive answer rendering, tool details, stop, refresh, and replay.
- Provider-backed live streaming is reported separately from deterministic test success. If provider credentials or a cancellable provider API are unavailable, do not claim live provider or hard-cancellation verification.

## Out of Scope

- WebSocket transport.
- Compatibility with the former `{token}`, `{error}`, and `[DONE]` stream format.
- Exposure or persistence of hidden chain-of-thought, raw internal reasoning, secrets, full tracebacks, or unredacted tool payloads.
- Multiple backend application workers, multiple backend replicas, Redis, a distributed event broker, or cross-process stream routing.
- Guaranteed force termination of a running Python thread, arbitrary tool subprocess, or provider request that does not offer cooperative cancellation.
- Concurrent Agent runs within the same conversation; one active generated response per conversation remains the MVP behaviour.
- Redesign of unrelated chat, upload, authentication, model configuration, or conversation features.
- Treating a mocked test as evidence of a successful real-provider end-to-end run.

## Further Notes

### Definition of done

The feature is complete only when all of the following are true:

1. Frontend and backend use only the version 1 event contract.
2. Answer, thinking, tool call, tool result, error, completion, and stopped paths are represented by tested structured events.
3. Browser-bound tool information is sanitised before persistence and transmission.
4. Stop is immediate at the product boundary, idempotent, preserves partial output, and cannot be overwritten by late results.
5. Refresh and reconnect resume from a sequence without re-running the Agent or duplicating visible content.
6. Event access is authenticated and authorised without placing credentials in the stream URL.
7. Focused backend tests, frontend tests, production build, and local browser smoke verification pass, with live-provider validation reported honestly and separately.
8. Stream cleanup regression coverage passes and no pending stream resources remain after any terminal path.
9. Documentation reflects the implemented flow and explicitly preserves the single-worker deployment boundary.

### Agreed product choices

- Text appears incrementally.
- The backend emits public thinking stages or summaries and sanitised tool call/result data; the frontend decides what to render.
- The frontend displays answer text directly, thinking as status, and tool activity in collapsed details.
- Users can stop generation and retain the partial response.
- SSE remains the transport, consumed through authenticated `fetch` streaming.
- The new protocol replaces the old format immediately; there is no legacy compatibility layer.
- Safe execution events persist for the lifetime of the conversation and support ordered replay.
- The current single-backend-worker topology is an explicit requirement for this version.
