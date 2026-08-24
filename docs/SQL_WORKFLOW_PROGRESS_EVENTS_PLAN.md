# SQL Workflow 前端執行步驟顯示開發計畫

狀態：MVP 已實作，待部署驗證

## Problem Statement

目前資料庫問題會在前端顯示一般 Agent 的「執行詳情」，但 `run_sql_workflow` 內部的 `plan`、`sql`、驗證、執行與 `repair` 階段，前端通常只能看到外層資料庫工具的活動。

當 SQL 生成或修復失敗時，使用者與維護者無法直接從網頁判斷錯誤發生在哪個階段，必須進入後台查看 log。這降低了除錯效率，也讓「SQL 沒有執行」、「SQL 執行失敗後修復」、「SQL 執行成功但結果驗證失敗」等情況難以區分。

## Solution

在現有的 Agent SSE 事件與前端「執行詳情」機制上，加入 SQL workflow 的結構化進度事件。

`run_sql_workflow` 在各階段開始、完成、驗證失敗、執行失敗與修復時，透過應用程式層的 progress event sink 發出安全化事件。後端沿用現有的事件佇列、事件清理、SQLite 保存、SSE 傳送與前端事件 reducer；前端將這些事件顯示在既有的「執行詳情」時間軸中。

第一版只顯示階段狀態與安全摘要，不顯示模型內部思考內容。SQL、Plan 與錯誤細節採取截斷、遮罩與權限控制後，才評估是否在後續版本提供可展開的除錯資訊。

## User Stories

1. As a database-question user, I want to see that the system is analysing my request, so that I know the request has entered the SQL workflow.
2. As a database-question user, I want to see when the query plan is being created, so that a long response does not appear stalled.
3. As a database-question user, I want to see when the SQL statement is being generated, so that I can distinguish planning from execution.
4. As a database-question user, I want to see whether SQL validation passed, so that I know the statement passed the pre-execution checks.
5. As a database-question user, I want to see when SQL execution starts, so that I understand the system is querying the database rather than still generating text.
6. As a database-question user, I want to see whether execution succeeded or failed, so that a failed query is not confused with a valid empty result.
7. As a database-question user, I want to see when SQL repair starts, so that I know the system is responding to a validation or database error.
8. As a database-question user, I want to see the repair attempt number, so that repeated repair attempts are understandable.
9. As a database-question user, I want to see when a repaired SQL statement is validated and executed again, so that the recovery process is auditable.
10. As a database-question user, I want the final answer to remain separate from execution details, so that technical information does not overwhelm the result.
11. As a database-question user, I want execution details to remain collapsed by default, so that the normal chat experience stays readable.
12. As a database-question user, I want the workflow timeline to remain available after the answer is complete, so that I can review how the answer was produced.
13. As a database-question user, I want the workflow timeline to survive a page refresh, so that a completed answer remains diagnosable.
14. As a database-question user, I want the workflow timeline to resume correctly after a temporary SSE interruption, so that events are not duplicated or lost.
15. As a database-question user, I want a clear terminal workflow status when the system cannot produce a valid result, so that I do not mistake an error explanation for database data.
16. As an administrator, I want to identify whether a failure happened in planning, SQL generation, validation, execution, repair, or final result validation, so that I can diagnose deployments without immediately opening backend logs.
17. As an administrator, I want the displayed SQL workflow error to be safe and concise, so that tracebacks, credentials, connection strings, and sensitive data are not exposed in the browser.
18. As an administrator, I want long SQL, Plan fields, and database errors to be truncated consistently, so that one event cannot overwhelm the chat or event store.
19. As an administrator, I want workflow events to follow the same conversation and message permissions as other execution events, so that users cannot inspect another user's SQL activity.
20. As an administrator, I want deleting a conversation to delete its workflow events, so that event retention follows the existing message lifecycle.
21. As a maintainer, I want SQL workflow progress to use the existing SSE transport, so that the first implementation does not introduce a second real-time protocol.
22. As a maintainer, I want `run_sql_workflow` to report progress through one explicit application-level seam, so that the workflow remains independent from HTTP, SQLite, and frontend code.
23. As a maintainer, I want non-database requests to continue using the existing Agent stream without SQL workflow events, so that this feature does not affect general, file, or search questions.
24. As a maintainer, I want stage events to be persisted before they are broadcast, so that reconnect and page refresh use one authoritative event history.
25. As a maintainer, I want stage event ordering to be deterministic, so that plan, SQL, validation, execution, repair, and final answer events appear in the actual observable order.
26. As a maintainer, I want late workflow events after a terminal message state to be ignored, so that a stopped or failed answer cannot be changed by delayed worker output.
27. As a test author, I want deterministic workflow events from fake Plan, SQL, repair, and execution stages, so that frontend and backend tests do not require a live provider or database.
28. As a test author, I want to verify a successful workflow, a validation repair, a SQL execution repair, a final failure, a stop, a reconnect, and a page reload, so that the feature is reliable across lifecycle paths.
29. As a deployer, I want the feature to work with the existing single-worker SSE deployment boundary, so that rollout does not require a new broker or multi-worker architecture.
30. As a user asking a non-database question, I want no SQL workflow progress to appear, so that unrelated answers remain unchanged.

## Implementation Decisions

### 1. Use one application-level progress seam

The primary seam is a progress event sink passed from the database workflow integration into `run_sql_workflow`.

The workflow must report stage progress through this sink, but must not directly write to SQLite, publish SSE frames, or import frontend concepts. The surrounding Agent worker remains responsible for placing events on the existing event queue.

This keeps the number of new architectural seams to one and preserves the existing separation between workflow logic and transport/persistence.

### 2. Reuse the existing SSE and persisted event pipeline

The new events use the existing sequence, timestamp, message ownership, persistence, replay, subscriber notification, and terminal-state rules.

The first implementation should extend the versioned event contract with a dedicated SQL workflow stage event rather than encoding stage information into arbitrary text. If the current contract cannot add a new event type without a protocol version change, the implementation must explicitly version the contract and update backend and frontend tests together.

### 3. Define a small stage event state model

Each event identifies:

- workflow name: SQL
- stage: planning, SQL generation, validation, execution, repair, or result validation
- status: started, completed, failed, skipped, or retrying
- repair attempt number when applicable
- short safe human-readable summary
- optional safe structured metadata such as duration or issue category

Stage events are progress records, not model reasoning transcripts. A stage may emit more than one event, but the sequence must remain monotonic and observable.

### 4. Emit events at meaningful boundaries

The minimum event points are:

- SQL workflow started
- Plan started and completed
- SQL generation started and completed
- pre-execution validation passed or failed
- SQL execution started, completed, or failed
- repair started, completed, or failed
- result validation passed or failed
- workflow completed or failed

The implementation should not emit one event for every model token. The Plan, SQL, and repair agents are currently non-streaming; boundary events provide useful progress without increasing provider streaming complexity.

### 5. Keep displayed data safe

Before persistence and transmission, workflow event payloads must use the existing browser sanitisation rules and add SQL-specific limits:

- never expose credentials, connection strings, bearer tokens, or environment values
- never expose raw Python tracebacks
- truncate SQL and Plan previews to a bounded size
- expose error category and safe database message rather than an unrestricted exception object
- avoid returning full database rows in progress events
- treat frontend collapsing as a presentation choice, not a security boundary

### 6. Preserve the existing user interface model

The frontend should add SQL workflow stages to the existing `執行詳情` timeline. The main answer remains directly visible, and execution details remain collapsed by default.

Stage labels should be user-readable Traditional Chinese while retaining machine-readable stage and status values for tests and future localization.

The UI should distinguish at least:

- in progress
- succeeded
- retrying
- failed
- skipped

### 7. Preserve non-database behavior

Only the database workflow integration emits SQL workflow stage events. General Agent, file, RAG, and other non-database flows must continue to use the existing event behavior and must not receive SQL-specific instructions or UI stages.

### 8. Make stopping and terminal behavior explicit

If the user stops a response, later workflow events must not be persisted or displayed after the stopped terminal event wins.

If repair attempts are exhausted, the workflow emits a safe failed stage and the final response must state that no valid database result was produced. It must not fabricate a result.

### 9. Keep the first release read-only and diagnostic

This feature only exposes progress for the existing read-oriented SQL workflow. It does not add SQL write operations, database administration controls, manual SQL editing, or a browser-side retry button.

## Testing Decisions

Tests should verify externally observable event contracts and user-visible behavior rather than private callback implementation details.

### Backend tests

Add focused tests covering:

- successful Plan → SQL → validation → execution flow
- validation failure followed by repair
- SQL execution failure followed by repair
- exhausted repair attempts
- result validation failure after successful SQL execution
- event type, payload shape, sequence ordering, and status transitions
- safe sanitisation, truncation, and secret removal
- persistence before live notification
- replay after `after_sequence`
- completed, failed, and stopped workflow histories
- ignoring late events after a terminal state
- conversation ownership and administrator access
- deletion of workflow events with the message or conversation
- non-database Agent flows producing no SQL workflow stage events

Existing backend streaming-event, message lifecycle, and SQL workflow tests should be extended before creating new test infrastructure.

### Frontend tests

Add focused tests covering:

- reducing workflow stage events into the correct message state
- duplicate sequence suppression and reconnect behavior
- stage ordering and retry attempt display
- collapsed execution details by default
- expanded timeline labels and status display
- safe rendering of truncated SQL or error previews
- page refresh hydration of completed workflow events
- stop and terminal states preventing later stage updates
- non-database messages remaining unchanged

Existing stream store and chat message component tests are the preferred seams.

### Integration and browser checks

Use a deterministic fake Agent/event source for most tests. Separately run a deployed browser smoke test for:

- one successful SQL workflow
- one repair workflow
- one exhausted-failure workflow if reproducible
- page refresh and conversation reopening
- SSE reconnection without duplicated stages

Provider-backed browser results must be reported separately from deterministic test success.

## Out of Scope

- Replacing SSE with WebSocket or another transport.
- Adding Redis, a distributed event broker, multiple backend workers, or horizontal stream routing.
- Showing unrestricted chain-of-thought or raw provider reasoning.
- Showing credentials, connection strings, raw tracebacks, or unrestricted database output.
- Adding arbitrary SQL write or administrative operations.
- Allowing users to edit and submit generated SQL from the browser.
- Adding a manual frontend retry control in the first version.
- Changing the classifier or forcing all requests through the SQL workflow.
- Replacing the current execution-details UI with a separate debugging console.
- Treating a successful SQL execution as proof that the natural-language result is semantically correct; result validation remains a separate concern.

## Further Notes

The feature is especially valuable because the current workflow has already shown distinct failure classes: SQL generation or execution failure, successful execution with incorrect ordering, blank-value categorisation, and inconsistent equivalent queries. A visible stage timeline will make those classes easier to reproduce and classify, but it will not itself fix semantic errors.

Recommended implementation order after approval:

1. Confirm the public event contract and sanitisation limits.
2. Add the progress sink seam and backend stage emission.
3. Add persistence, replay, stop, and terminal-state tests.
4. Add frontend reducer and timeline rendering.
5. Run focused backend/frontend tests.
6. Run deployed browser smoke tests and compare stage-level evidence with the existing SQL test reports.

The initial acceptance criterion is not merely that the UI shows more text. It is that an operator can identify the failing SQL workflow stage from the browser, while non-database conversations and existing SSE lifecycle behavior remain unchanged.
