# 分階段 SQL Agent 生成與驗證規格

> 狀態：第一階段已實作，已通過 backend 測試；Gemma 4:26B / production E2E 尚未驗證
>
> 本文件依目前討論整理，先確認流程與邊界，再進行程式修改。

## Problem Statement

目前 HERANCHAT 使用單一 Agent 處理使用者問題。Agent 同時負責判斷問題類型、選擇工具、讀取 Knowledge、理解業務意圖、生成 SQL、執行 SQL，以及整理自然語言答案。

這種流程對 `gemma4:26b` 有幾個風險：

- 模型可能已讀取規則，卻漏掉必要條件。
- 模型可能選錯 entity grain，將名稱當成唯一識別。
- 模型可能使用不完整 JOIN key。
- 模型可能把描述性主檔使用 `INNER JOIN`，意外縮小資料母體。
- 模型可能在生成 SQL 時同時改變 metric、日期、filters 與排序邏輯。
- 模型自行進行「最後檢查」時，可能只是重述原本的錯誤。

目前的 SQL Knowledge 已經可以被 `check_rules_tool` 與 `get_db_table_content` 共用，但規則被模型執行的順序仍不是程式可控制的流程。

本規格只處理「已經判斷為資料庫問題」的後續 SQL 生成流程。一般聊天、檔案問答、網路搜尋與其他非資料庫問題不在本規格的改動範圍內。

## Solution

在資料庫問題分支中，將目前單次 Agent 呼叫拆成由應用程式控制的多階段流程：

1. 產生結構化 Query Plan。
2. 由程式驗證 Query Plan。
3. 根據已驗證的 Query Plan 生成 SQL 初稿。
4. 由程式驗證 SQL 是否符合 Plan、Knowledge 與 SQL Server 基本規則。
5. 驗證通過後執行 SQL。
6. 若 SQL 驗證或執行失敗，將具體錯誤交給 SQL Repair Agent 修復。
7. 修復後重新驗證並執行；成功後才產生自然語言答案。

Query Plan 與 SQL 生成不應由同一個自由形式的模型回覆一次完成。每一階段只負責一種決策，並將上一階段的結果作為下一階段的受控輸入。

## User Stories

1. As a user asking a database question, I want the system to identify the requested business metric before generating SQL, so that order count, quantity, amount, and price variation are not silently exchanged.
2. As a user asking for product results, I want the system to identify the stable product key separately from the product name, so that products with the same name are not merged.
3. As a user asking for salesperson results, I want the system to group by the salesperson identifier and use the name for display, so that people with the same name are not merged.
4. As a user providing an explicit date range, I want the date range preserved exactly, so that the system does not replace it with a relative period or `GETDATE()`.
5. As a user asking for a comparison, I want the system to identify the required comparison periods before generating SQL, so that the result does not compare unintended periods.
6. As a user asking for sales data, I want the system to select the correct base table, so that the aggregation is not based on an incidental lookup table.
7. As a user asking for sales data, I want document, enterprise, site, item, and other required keys to be identified before SQL generation, so that joins do not multiply or lose records.
8. As a user asking for a descriptive product name, I want the system to preserve base sales records when a lookup row is absent, so that missing master data does not silently remove sales.
9. As a user asking for a ranking, I want the ranking metric, ordering, and result limit to be consistent, so that TOP results represent the requested metric.
10. As a user asking for a difference or variation, I want the system to verify that enough valid observations exist, so that one observation is not presented as a meaningful difference.
11. As a user asking about a category, I want NULL and blank categories handled explicitly, so that they are not silently relabeled as an existing business category.
12. As a user, I want a failed SQL query to be repaired using the actual error, so that the system does not fabricate a result or silently change my question.
13. As a user asking a non-database question, I want the existing general-answer flow to remain unchanged, so that SQL planning does not pollute unrelated answers.
14. As a user asking a file question, I want the file-answer flow to remain available, so that the database workflow does not intercept file content questions.
15. As a user asking a mixed question, I want only the database-dependent portion to enter the SQL workflow, so that general explanation and database lookup can coexist.
16. As a user, I want SQL generation to finish with a valid database result before receiving a confident natural-language answer, so that failed execution is visible as a limitation.
17. As an operator, I want internal Plan, validation, repair, and execution events to remain observable, so that SQL failures can be diagnosed from the existing Agent execution details.
18. As an operator, I want non-database requests to avoid loading the full database Knowledge, so that unrelated requests do not incur unnecessary context or latency.
19. As a maintainer, I want `check_rules_tool` and `get_db_table_content` to use one Knowledge source, so that rules do not drift between tools.
20. As a maintainer, I want the SQL workflow to use the existing streaming answer contract, so that the frontend does not need a new response protocol for the first implementation.
21. As a maintainer, I want each intermediate stage to have a bounded output format, so that a small model cannot hide decisions inside long free-form reasoning.
22. As a maintainer, I want the system to stop after a bounded number of repairs, so that an invalid query does not enter an endless Agent loop.
23. As a maintainer, I want SQL validation to be independent of the model's self-assessment, so that the model cannot declare an invalid SQL plan valid by itself.
24. As a test author, I want existing Text-to-SQL cases to exercise the full staged path, so that the new workflow can be compared with the current baseline.
25. As a deployer, I want the staged workflow to use the existing backend deployment boundary, so that rollout does not require a new frontend deployment for the initial version.

## Implementation Decisions

### Scope and routing boundary

- This workflow starts only after the existing or future request classifier has selected the database mode.
- The classifier is not part of this spec.
- Non-database requests continue through their existing Agent path.
- The SQL workflow must not be added as a mandatory preamble to the global system prompt for every request.

### Preferred orchestration seam

- Use one application-level orchestration seam between database-mode selection and the existing final answer stream.
- The orchestrator, rather than the model, controls stage order, validation, retry count, and transition to SQL execution.
- The existing final answer streaming path remains the user-facing output boundary.
- Internal Plan and SQL-generation calls may be non-streaming; their intermediate text must not be emitted as the final answer.

### Stage 1: Query Plan generation

The Plan Agent receives the user question and the relevant verified Knowledge. It returns only a structured Query Plan with these fields:

- intent
- metric
- entity key
- display fields
- base table
- required and descriptive joins
- complete join keys
- filters
- date column and half-open date range
- grouping grain
- HAVING requirement
- ordering and result limit
- NULL and blank-value policy

The Plan Agent does not generate SQL and does not execute tools.

### Stage 1: Query Plan validation

The application validates the Plan before allowing SQL generation. Validation must reject or request clarification when:

- the metric does not match the user request;
- the entity key is absent, is a display name, or is not verified by Knowledge;
- the base table is missing or not compatible with the metric;
- a required business join lacks a complete key;
- an explicit user date or filter is missing or changed;
- a comparison lacks the required observations/HAVING decision;
- a NULL or blank policy is absent where a dimension is selected;
- a TOP value or ordering metric is inconsistent with the requested ranking.

The validator should return machine-readable violations. It should not ask the model to decide whether its own Plan is valid.

### Stage 2: SQL generation

The SQL Agent receives:

- the original user question;
- the validated Query Plan;
- only the relevant Knowledge/schema content needed for the Plan;
- a strict instruction to return SQL Server T-SQL only.

The SQL Agent must preserve the Plan's metric, entity key, dates, filters, join keys, grouping, ordering, and limit. It must not add a natural-language answer in this stage.

The first implementation should prefer a relevant schema slice over repeatedly presenting unrelated tables when the required schema boundaries are known. Full Knowledge remains available as the source of truth when the relevant slice cannot be determined safely.

### Stage 3: SQL validation

The application validates the generated SQL against the validated Plan before execution. The first implementation should check at least:

- allowed database/table naming and T-SQL shape;
- referenced tables and columns against verified Knowledge;
- entity key presence in SELECT/GROUP BY as applicable;
- display-name aggregation or grouping behavior;
- complete compound JOIN keys;
- descriptive lookup JOIN type and purpose;
- preservation of explicit date ranges and filters;
- metric consistency across SELECT, HAVING, ORDER BY, and TOP;
- NULL/blank handling;
- accidental use of dynamic dates;
- SQL-only output without HTML or answer prose.

The validator should report concrete violations, such as a missing `smdob_014='1'` filter or an inappropriate `INNER JOIN` to a descriptive table.

### Stage 4: SQL repair

- Repair runs only after a validator violation or a concrete SQL execution error.
- The repair input contains the original question, the immutable Query Plan, the SQL candidate, and the exact violations/error.
- The repair Agent may change SQL syntax, aliases, joins, or expressions required to resolve the violation, but may not change the user's metric, dates, filters, entity key, or requested result limit.
- The repaired SQL must pass the same validator again before execution.
- The initial implementation allows a bounded repair count, recommended as one repair attempt per failure class and a hard overall limit of two attempts.
- If repair remains invalid or execution fails after the limit, the system returns a clear limitation instead of fabricating an answer.

### Stage 5: SQL execution and final answer

- SQL execution happens only after validation passes.
- A successful result is passed to the existing final answer stage.
- The final answer may explain metric and filter choices, but must not claim a result when execution failed.
- The SQL and relevant execution metadata continue to use the existing Agent event and answer presentation contract.

### Tool and Knowledge boundaries

- `check_rules_tool` and `get_db_table_content` continue to read the same Knowledge source.
- SQL-specific tools are exposed to the database workflow; non-database workflows should not receive the SQL workflow as a mandatory instruction.
- The staged workflow must not depend on the model voluntarily calling `check_rules_tool` in the correct order.
- The application controls whether each stage is allowed to proceed.

### Agent cache and deployment

- The implementation must account for the existing Agent cache and startup preload behavior.
- A Knowledge change must be visible to newly created SQL-stage agents without requiring a frontend change.
- If Knowledge content is included in an Agent's construction-time prompt, its version must participate in the cache key, or the SQL-stage agent must be rebuilt when Knowledge changes.
- The bind-mounted Knowledge deployment remains valid; the workflow must not require an image rebuild for prompt-only changes.

## Testing Decisions

### Test seam

The primary seam is the application-level database workflow orchestrator. Tests should verify external stage behavior and contracts rather than implementation details of the underlying LLM library.

### Unit and contract tests

Add focused tests for:

- Query Plan parsing and required fields;
- rejection of a name-only entity key;
- rejection of incomplete compound JOIN keys;
- preservation of explicit dates and filters;
- detection of missing sales/return default filters;
- detection of an inappropriate descriptive-table INNER JOIN;
- metric/order/TOP consistency;
- NULL and blank policy requirements;
- bounded repair behavior;
- no final answer after failed execution;
- successful result handoff to the existing answer stage.

### Existing Text-to-SQL tests

Reuse the existing ten-case Text-to-SQL ground-truth set and remote runner. The cases cover product ranking, return counts/quantities, price variation, sales amount/category, period comparison, and salesperson ranking.

The runner should capture, where available:

- selected workflow mode;
- Query Plan;
- generated SQL;
- validator violations;
- repair attempts;
- executed SQL;
- terminal event;
- final result/error.

Exact SQL string equality is not sufficient as the only acceptance criterion. SQL semantic equivalence and required business invariants should be checked separately.

### Regression tests for non-database behavior

Run representative general questions, file questions, and search questions to verify that:

- they do not load the SQL workflow;
- they do not call SQL tools;
- they retain the current answer behavior;
- they do not incur SQL-stage repair or execution events.

### Live browser verification

After deployment, run at least one database question through the real website and inspect:

- visible result;
- generated SQL source;
- execution details showing the staged events where exposed;
- browser console errors;
- correct behavior after a fresh conversation.

Live browser success does not replace deterministic validator and focused tests.

### Failure-oriented acceptance cases

At minimum, verify that the workflow catches or repairs:

- product name used as the only grouping key;
- same-name products with different product IDs being merged;
- missing `site` in a compound JOIN;
- unnecessary `INNER JOIN` to `wmmta`;
- missing `smdob_014='1'` or `smdob_loc<>'AU'`;
- explicit 2025 dates replaced with a relative date;
- `SUM(smdob_qty)` used when the question asks for order count;
- comparison query with insufficient valid observations;
- NULL/blank category mapped to `其他`;
- SQL execution failure followed by an invented answer.

## Out of Scope

- Building or changing the general-purpose request classifier.
- Changing the behavior of non-database Agent workflows.
- Replacing the underlying Akasha Agent library.
- Guaranteeing perfect SQL from the model without deterministic validation.
- Adding new database tables, indexes, or schema migrations.
- Changing the MSSQL connection or credential configuration.
- Redesigning the frontend chat UI.
- Changing the existing SSE transport contract in the first implementation.
- Automatically publishing or deploying the implementation.
- Rewriting the entire Knowledge schema when the issue can be solved by selecting a relevant subset.
- Supporting arbitrary SQL write operations; this workflow remains read-oriented.

## Further Notes

The main expected benefit is not that the model becomes more capable. The benefit is that the model no longer has to make all decisions in one generation, and deterministic code can reject an invalid intermediate result before it reaches the database.

The staged workflow should be evaluated against the current single-Agent baseline. It should be accepted only if it improves required SQL invariants without regressing general, file, or search responses.

The first implementation should keep the number of seams small: one database orchestration seam, one Plan contract, and one SQL validator contract. Additional specialized agents or complex retrieval should wait until the focused workflow has measurable results.
