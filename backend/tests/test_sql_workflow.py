import json

import pytest

from backend.sql_workflow import (
    QueryPlanValidationError,
    parse_query_plan,
    normalise_query_plan,
    run_sql_workflow,
    validate_query_plan,
    validate_sql,
)


def valid_plan() -> dict:
    return {
        "intent": "查詢銷售訂單次數最多的產品",
        "metric": "COUNT_DISTINCT(smdob_docno)",
        "entity_key": ["smdob_ent", "smdob_site", "smdob_itemno"],
        "display_fields": ["wmmta.wmmta_itemname"],
        "base_table": "smdob",
        "joins": [
            {
                "table": "smdoa",
                "join_type": "required",
                "keys": ["ent", "site", "docno"],
            },
            {
                "table": "wmmta",
                "join_type": "descriptive",
                "keys": ["ent", "site", "itemno"],
            },
        ],
        "filters": [
            "smdoa_stus = 'S'",
            "smdob_014 = '1'",
            "smdob_loc <> 'AU'",
        ],
        "date_range": {
            "column": "smdoa_pstdt",
            "start": "2025-01-01",
            "end": "2026-01-01",
        },
        "group_by": ["smdob_ent", "smdob_site", "smdob_itemno"],
        "having": None,
        "order_by": "metric DESC",
        "top": 10,
        "null_policy": "display name may be NULL; do not merge entities",
    }


def test_parse_query_plan_accepts_json_code_fence():
    raw = "```json\n" + json.dumps(valid_plan()) + "\n```"

    assert parse_query_plan(raw) == valid_plan()


def test_parse_query_plan_rejects_non_object():
    with pytest.raises(QueryPlanValidationError, match="JSON object"):
        parse_query_plan("[1, 2, 3]")


def test_validate_query_plan_rejects_display_name_as_only_entity_key():
    plan = valid_plan()
    plan["entity_key"] = ["wmmta_itemname"]

    issues = validate_query_plan(plan)

    assert any("stable entity key" in issue for issue in issues)


def test_validate_query_plan_rejects_incomplete_compound_join():
    plan = valid_plan()
    plan["joins"][0]["keys"] = ["docno"]

    issues = validate_query_plan(plan)

    assert any("smdoa" in issue and "ent/site/docno" in issue for issue in issues)


def test_validate_query_plan_rejects_explicit_date_replaced_by_dynamic_date():
    plan = valid_plan()
    plan["date_range"]["start"] = "GETDATE()"

    issues = validate_query_plan(plan)

    assert any("explicit date" in issue.lower() for issue in issues)


def test_normalise_query_plan_accepts_common_llm_aliases_without_relaxing_keys():
    plan = {
        "intent": "sales by product",
        "metric": "SUM(smdob.smdob_qty)",
        "entity_key": "smdob.smdob_itemno",
        "display_fields": ["smdob.smdob_itemno", "wmmta.wmmta_itemname"],
        "base_table": "[HERAN].[dbo].[smdob]",
        "joins": [
            {
                "join_type": "INNER JOIN",
                "target_table": "[HERAN].[dbo].[smdoa]",
                "keys": [
                    "smdob.smdob_ent = smdoa.smdoa_ent",
                    "smdob.smdob_site = smdoa.smdoa_site",
                    "smdob.smdob_docno = smdoa.smdoa_docno",
                ],
            },
            {
                "join_type": "LEFT JOIN",
                "target_table": "wmmta",
                "keys": [
                    "smdob.smdob_ent = wmmta.wmmta_ent",
                    "smdob.smdob_site = wmmta.wmmta_site",
                    "smdob.smdob_itemno = wmmta.wmmta_itemno",
                ],
            },
        ],
        "filters": [],
        "date_range": {"field": "smdoa.smdoa_pstdt", "start": "2025-01-01", "end": "2025-04-01"},
        "group_by": ["smdob.smdob_itemno", "wmmta.wmmta_itemname"],
        "having": [],
        "order_by": [{"field": "SUM(smdob.smdob_qty)", "direction": "DESC"}],
        "limit": None,
        "null_policy": {},
    }

    normalised = normalise_query_plan(plan)

    assert normalised["entity_key"] == ["smdob_itemno"]
    assert normalised["date_range"]["column"] == "smdoa.smdoa_pstdt"
    assert normalised["top"] is None
    assert normalised["joins"][0]["table"] == "smdoa"
    assert normalised["joins"][0]["keys"] == ["ent", "site", "docno"]
    assert validate_query_plan(normalised) == []


def test_validate_query_plan_accepts_an_explicitly_unbounded_date_range():
    plan = valid_plan()
    plan["date_range"] = {"column": None, "start": None, "end": None}

    assert validate_query_plan(plan) == []


def test_normalise_query_plan_adds_an_unbounded_date_range_when_omitted():
    plan = valid_plan()
    plan.pop("date_range")

    normalised = normalise_query_plan(plan)

    assert normalised["date_range"] == {"column": None, "start": None, "end": None}
    assert validate_query_plan(normalised) == []


def test_normalise_query_plan_canonicalises_bracketed_group_fields():
    plan = valid_plan()
    plan["group_by"] = ["[HERAN].[dbo].[smdob].[smdob_itemno]"]

    normalised = normalise_query_plan(plan)

    assert normalised["group_by"] == ["smdob_itemno"]


def test_validate_sql_skips_date_predicates_for_an_unbounded_plan():
    plan = valid_plan()
    plan["date_range"] = {"column": None, "start": None, "end": None}
    sql = valid_sql().replace(
        "  AND smdoa.smdoa_pstdt >= '2025-01-01'\n"
        "  AND smdoa.smdoa_pstdt < '2026-01-01'\n",
        "",
    )

    assert validate_sql(sql, plan) == []


def valid_sql() -> str:
    return """
SELECT TOP 10
    smdob.smdob_itemno,
    MIN(wmmta.wmmta_itemname) AS product_name,
    COUNT(DISTINCT smdob.smdob_docno) AS metric
FROM [HERAN].[dbo].[smdob] AS smdob
JOIN [HERAN].[dbo].[smdoa] AS smdoa
  ON smdoa.smdoa_ent = smdob.smdob_ent
 AND smdoa.smdoa_site = smdob.smdob_site
 AND smdoa.smdoa_docno = smdob.smdob_docno
LEFT JOIN [HERAN].[dbo].[wmmta] AS wmmta
  ON wmmta.wmmta_ent = smdob.smdob_ent
 AND wmmta.wmmta_site = smdob.smdob_site
 AND wmmta.wmmta_itemno = smdob.smdob_itemno
WHERE smdoa.smdoa_stus = 'S'
  AND smdob.smdob_014 = '1'
  AND smdob.smdob_loc <> 'AU'
  AND smdoa.smdoa_pstdt >= '2025-01-01'
  AND smdoa.smdoa_pstdt < '2026-01-01'
GROUP BY smdob.smdob_ent, smdob.smdob_site, smdob.smdob_itemno
ORDER BY metric DESC;
"""


def test_validate_sql_accepts_plan_compliant_sql():
    assert validate_sql(valid_sql(), valid_plan()) == []


def test_validate_sql_rejects_missing_required_filter():
    sql = valid_sql().replace("  AND smdob.smdob_loc <> 'AU'\n", "")

    issues = validate_sql(sql, valid_plan())

    assert any("smdob_loc" in issue for issue in issues)


def test_validate_sql_rejects_inner_join_for_descriptive_table():
    sql = valid_sql().replace("LEFT JOIN [HERAN].[dbo].[wmmta]", "JOIN [HERAN].[dbo].[wmmta]")

    issues = validate_sql(sql, valid_plan())

    assert any("wmmta" in issue and "LEFT JOIN" in issue for issue in issues)


def test_validate_sql_rejects_incomplete_document_join():
    sql = valid_sql().replace(
        " AND smdoa.smdoa_site = smdob.smdob_site\n", ""
    )

    issues = validate_sql(sql, valid_plan())

    assert any("smdoa" in issue and "ent/site/docno" in issue for issue in issues)


def test_validate_sql_rejects_dynamic_date_for_explicit_range():
    sql = valid_sql().replace("'2025-01-01'", "GETDATE()", 1)

    issues = validate_sql(sql, valid_plan())

    assert any("date" in issue.lower() for issue in issues)


def test_run_sql_workflow_validates_plan_before_generating_sql():
    calls = []

    def plan_agent(question, knowledge):
        calls.append("plan")
        invalid = valid_plan()
        invalid["entity_key"] = ["wmmta_itemname"]
        return json.dumps(invalid)

    def sql_agent(*args):
        calls.append("sql")
        return valid_sql()

    with pytest.raises(QueryPlanValidationError, match="stable entity key"):
        run_sql_workflow(
            "查詢產品",
            knowledge="knowledge",
            plan_agent=plan_agent,
            sql_agent=sql_agent,
            repair_agent=lambda *args: valid_sql(),
            execute_sql=lambda sql: {"ok": True},
        )

    assert calls == ["plan"]


def test_run_sql_workflow_reports_stage_progress_through_one_callback():
    events = []

    result = run_sql_workflow(
        "查詢產品",
        knowledge="knowledge",
        plan_agent=lambda question, knowledge: json.dumps(valid_plan()),
        sql_agent=lambda question, plan, knowledge: valid_sql(),
        repair_agent=lambda *args: valid_sql(),
        execute_sql=lambda sql: {"ok": True, "result_markdown": "| product |"},
        on_stage=events.append,
    )

    assert result.repair_attempts == 0
    assert [(event["stage"], event["status"]) for event in events] == [
        ("planning", "started"),
        ("planning", "completed"),
        ("sql_generation", "started"),
        ("sql_generation", "completed"),
        ("validation", "passed"),
        ("execution", "started"),
        ("execution", "completed"),
        ("result_validation", "completed"),
    ]


def test_run_sql_workflow_reports_repair_progress_after_execution_failure():
    events = []
    executions = iter([
        {"ok": False, "message": "invalid column name"},
        {"ok": True, "result_markdown": "| repaired |"},
    ])

    result = run_sql_workflow(
        "查詢產品",
        knowledge="knowledge",
        plan_agent=lambda question, knowledge: json.dumps(valid_plan()),
        sql_agent=lambda question, plan, knowledge: valid_sql(),
        repair_agent=lambda sql, plan, issues, knowledge: valid_sql(),
        execute_sql=lambda sql: next(executions),
        on_stage=events.append,
    )

    assert result.repair_attempts == 1
    assert [(event["stage"], event["status"]) for event in events] == [
        ("planning", "started"),
        ("planning", "completed"),
        ("sql_generation", "started"),
        ("sql_generation", "completed"),
        ("validation", "passed"),
        ("execution", "started"),
        ("execution", "failed"),
        ("repair", "started"),
        ("repair", "completed"),
        ("validation", "passed"),
        ("execution", "started"),
        ("execution", "completed"),
        ("result_validation", "completed"),
    ]
    assert events[7]["attempt"] == 1


def test_run_sql_workflow_repairs_sql_before_execution():
    calls = []
    bad_sql = valid_sql().replace("  AND smdob.smdob_loc <> 'AU'\n", "")

    def plan_agent(question, knowledge):
        calls.append("plan")
        return json.dumps(valid_plan())

    def sql_agent(question, plan, knowledge):
        calls.append("sql")
        return bad_sql

    def repair_agent(sql, plan, issues, knowledge):
        calls.append(("repair", tuple(issues)))
        return valid_sql()

    def execute_sql(sql):
        calls.append("execute")
        return {"ok": True, "result_markdown": "ok"}

    result = run_sql_workflow(
        "查詢產品",
        knowledge="knowledge",
        plan_agent=plan_agent,
        sql_agent=sql_agent,
        repair_agent=repair_agent,
        execute_sql=execute_sql,
    )

    assert result.execution["ok"] is True
    assert result.repair_attempts == 1
    assert [item if isinstance(item, str) else item[0] for item in calls] == [
        "plan",
        "sql",
        "repair",
        "execute",
    ]


def test_run_sql_workflow_repairs_database_error_before_returning():
    calls = []

    def plan_agent(question, knowledge):
        return json.dumps(valid_plan())

    def sql_agent(question, plan, knowledge):
        return valid_sql()

    def repair_agent(sql, plan, issues, knowledge):
        calls.append(issues)
        return valid_sql()

    outcomes = iter([
        {"ok": False, "error_type": "DatabaseError", "message": "invalid column"},
        {"ok": True, "result_markdown": "ok"},
    ])

    result = run_sql_workflow(
        "查詢產品",
        knowledge="knowledge",
        plan_agent=plan_agent,
        sql_agent=sql_agent,
        repair_agent=repair_agent,
        execute_sql=lambda sql: next(outcomes),
    )

    assert result.execution["ok"] is True
    assert result.repair_attempts == 1
    assert any("invalid column" in issue for issue in calls[0])


def test_database_query_tool_wraps_the_staged_workflow(monkeypatch):
    import backend.tools as tools

    class FakeConnection:
        def close(self):
            pass

    stage_prompts = []

    def fake_stage_agent(cfg, system_prompt):
        stage_prompts.append(system_prompt)
        if "Query Plan stage" in system_prompt:
            return lambda **kwargs: json.dumps(valid_plan())
        if "SQL generation stage" in system_prompt:
            return lambda **kwargs: valid_sql()
        return lambda **kwargs: valid_sql()

    monkeypatch.setattr(tools, "get_connection", lambda: FakeConnection())
    monkeypatch.setattr(
        tools,
        "load_llm_config",
        lambda db: {
            "model_name": "test:model",
            "temperature": 0.0,
            "max_input_tokens": 4096,
            "max_output_tokens": 4096,
        },
    )
    monkeypatch.setattr(tools, "get_db_table_content", lambda: "verified knowledge")
    monkeypatch.setattr(tools, "_build_sql_stage_agent", fake_stage_agent)
    monkeypatch.setattr(tools, "execute_sql_query", lambda sql: {"ok": True, "result_markdown": "ok"})

    result = json.loads(tools.database_query_function("查詢產品"))

    assert result["ok"] is True
    assert result["plan"]["metric"] == "COUNT_DISTINCT(smdob_docno)"
    assert result["repair_attempts"] == 0
    assert len(stage_prompts) == 3
    assert "[HERAN].[dbo]" in stage_prompts[1]
    assert "TOP" in stage_prompts[1]


def test_database_query_tool_forwards_workflow_stage_events_to_progress_sink(monkeypatch):
    import backend.tools as tools

    class FakeConnection:
        def close(self):
            pass

    events = []

    def fake_stage_agent(cfg, system_prompt):
        if "Query Plan stage" in system_prompt:
            return lambda **kwargs: json.dumps(valid_plan())
        return lambda **kwargs: valid_sql()

    monkeypatch.setattr(tools, "get_connection", lambda: FakeConnection())
    monkeypatch.setattr(
        tools,
        "load_llm_config",
        lambda db: {
            "model_name": "test:model",
            "temperature": 0.0,
            "max_input_tokens": 4096,
            "max_output_tokens": 4096,
        },
    )
    monkeypatch.setattr(tools, "get_db_table_content", lambda: "verified knowledge")
    monkeypatch.setattr(tools, "_build_sql_stage_agent", fake_stage_agent)
    monkeypatch.setattr(tools, "execute_sql_query", lambda sql: {"ok": True})

    token = tools.set_sql_workflow_progress_sink(events.append)
    try:
        result = json.loads(tools.database_query_function("查詢產品"))
    finally:
        tools.reset_sql_workflow_progress_sink(token)

    assert result["ok"] is True
    assert [event["stage"] for event in events] == [
        "planning",
        "planning",
        "sql_generation",
        "sql_generation",
        "validation",
        "execution",
        "execution",
        "result_validation",
    ]
