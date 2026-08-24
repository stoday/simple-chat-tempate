"""Small, deterministic contracts for the staged database workflow.

The LLM proposes a plan or SQL candidate. These functions decide whether the
candidate is structurally safe to pass to the next stage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


class QueryPlanValidationError(ValueError):
    """Raised when an LLM response cannot be parsed as a Query Plan."""


class SqlWorkflowError(RuntimeError):
    """Raised when the staged SQL workflow cannot produce a safe result."""


@dataclass(frozen=True)
class SqlWorkflowResult:
    plan: dict[str, Any]
    sql: str
    execution: Mapping[str, Any]
    repair_attempts: int


_REQUIRED_PLAN_FIELDS = (
    "intent",
    "metric",
    "entity_key",
    "display_fields",
    "base_table",
    "joins",
    "filters",
    "date_range",
    "group_by",
    "order_by",
    "top",
    "null_policy",
)

_COMPOUND_JOIN_KEYS = {
    "smdoa": {"ent", "site", "docno"},
    "smsra": {"ent", "site", "docno"},
    "wmmta": {"ent", "site", "itemno"},
    "smrta": {"ent", "site", "code"},
}

_COMPOUND_JOIN_LABELS = {
    "smdoa": "ent/site/docno",
    "smsra": "ent/site/docno",
    "wmmta": "ent/site/itemno",
    "smrta": "ent/site/code",
}

_DEFAULT_NULL_POLICY = (
    "Keep NULL and blank dimensions separate; label them as unclassified only "
    "for display and never merge them into an existing business category."
)


def parse_query_plan(raw: str) -> dict[str, Any]:
    """Parse a JSON Query Plan returned by a planning model."""

    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueryPlanValidationError(f"Query Plan is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise QueryPlanValidationError("Query Plan must be a JSON object")
    return value


def _short_table_name(value: Any) -> str:
    text = str(value or "").strip().strip("[]")
    parts = [part.strip().strip("[]") for part in text.split(".")]
    return parts[-1].lower() if parts else ""


def _canonical_plan_identifier(value: Any) -> Any:
    if not isinstance(value, str) or "(" in value:
        return value
    text = re.sub(r"\[([^]]+)\]", r"\1", value.strip())
    return text.split(".")[-1] if "." in text else text


def normalise_query_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Convert common LLM field aliases to the internal plan contract.

    This adapter accepts harmless naming differences, but derives compound join
    keys only from the model's explicit ON expression. Missing keys therefore
    remain invalid and are still rejected by ``validate_query_plan``.
    """

    normalised = dict(plan)

    entity_key = normalised.get("entity_key")
    if isinstance(entity_key, str):
        normalised["entity_key"] = [entity_key]
    if isinstance(normalised.get("entity_key"), list):
        normalised["entity_key"] = [
            _canonical_plan_identifier(value) for value in normalised["entity_key"]
        ]

    if isinstance(normalised.get("group_by"), list):
        normalised["group_by"] = [
            _canonical_plan_identifier(value) for value in normalised["group_by"]
        ]

    date_range = normalised.get("date_range")
    if isinstance(date_range, Mapping):
        date_range = dict(date_range)
        if "column" not in date_range and "field" in date_range:
            date_range["column"] = date_range["field"]
        normalised["date_range"] = date_range
    else:
        normalised["date_range"] = {"column": None, "start": None, "end": None}

    if "top" not in normalised and "limit" in normalised:
        normalised["top"] = normalised["limit"]
    normalised.setdefault("top", None)

    if not normalised.get("null_policy"):
        normalised["null_policy"] = _DEFAULT_NULL_POLICY

    joins = normalised.get("joins")
    if isinstance(joins, list):
        converted_joins: list[Any] = []
        for raw_join in joins:
            if not isinstance(raw_join, Mapping):
                converted_joins.append(raw_join)
                continue
            join = dict(raw_join)
            table = _short_table_name(join.get("table") or join.get("target_table"))
            if table:
                join["table"] = table
            if "join_type" not in join and "type" in join:
                join["join_type"] = join["type"]
            if "join_type" in join:
                join["join_type"] = re.sub(
                    r"\s+join$", "", str(join["join_type"]).strip().lower()
                )
            required_keys = _COMPOUND_JOIN_KEYS.get(table, set())
            raw_keys = [str(value).strip().lower() for value in join.get("keys", [])]
            key_source = " ".join(raw_keys)
            key_source += " " + str(join.get("on", ""))
            join["keys"] = [
                key for key in ("ent", "site", "docno", "itemno", "code")
                if key in required_keys
                and (key in raw_keys or re.search(rf"_{key}\b", key_source, flags=re.IGNORECASE))
            ]
            converted_joins.append(join)
        normalised["joins"] = converted_joins

    base_table = _short_table_name(normalised.get("base_table"))
    if base_table:
        normalised["base_table"] = base_table
    return normalised


def _clean_sql_candidate(sql: str) -> str:
    text = str(sql).strip()
    fenced = re.fullmatch(r"```(?:sql|tsql)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text


def validate_query_plan(plan: Mapping[str, Any]) -> list[str]:
    """Return deterministic violations for a proposed Query Plan."""

    issues: list[str] = []
    for field in _REQUIRED_PLAN_FIELDS:
        if field not in plan:
            issues.append(f"Missing Query Plan field: {field}")

    entity_key = plan.get("entity_key")
    if not isinstance(entity_key, list) or not entity_key or not all(
        isinstance(value, str) and value.strip() for value in entity_key
    ):
        issues.append("A stable entity key is required")
    elif len(entity_key) == 1 and any(
        marker in entity_key[0].lower() for marker in ("name", "itemname", "display")
    ):
        issues.append("A stable entity key cannot be a display name alone")

    date_range = plan.get("date_range")
    if not isinstance(date_range, dict):
        issues.append("A date_range object is required")
    else:
        raw_start = date_range.get("start")
        raw_end = date_range.get("end")
        raw_column = date_range.get("column")
        empty_values = {None, "", "none", "null", "n/a", "na", "not applicable"}
        unbounded = all(
            value is None or str(value).strip().casefold() in empty_values
            for value in (raw_column, raw_start, raw_end)
        )
        start = "" if raw_start is None else str(raw_start)
        end = "" if raw_end is None else str(raw_end)
        if not unbounded:
            if not start or not end or not raw_column:
                issues.append("date_range requires column, start, and end")
            if any(value.upper().startswith(("GETDATE", "CURRENT_DATE", "NOW")) for value in (start, end)):
                issues.append("Explicit date ranges cannot be replaced by a dynamic date")
            if start and end and start >= end and not any(
                value.upper().startswith(("GETDATE", "CURRENT_DATE", "NOW")) for value in (start, end)
            ):
                issues.append("date_range start must be earlier than end")

    joins = plan.get("joins")
    if not isinstance(joins, list):
        issues.append("joins must be a list")
    else:
        for join in joins:
            if not isinstance(join, dict):
                issues.append("Each join must be an object")
                continue
            table = str(join.get("table", "")).lower()
            keys = {str(key).lower() for key in join.get("keys", [])}
            required_keys = _COMPOUND_JOIN_KEYS.get(table)
            if required_keys and not required_keys.issubset(keys):
                issues.append(
                    f"Join {table} must declare complete {_COMPOUND_JOIN_LABELS[table]} keys"
                )
            if table == "wmmta" and str(join.get("join_type", "")).lower() not in {
                "left",
                "descriptive",
            }:
                issues.append("Descriptive wmmta join must be LEFT JOIN")

    if not isinstance(plan.get("filters"), list):
        issues.append("filters must be a list")
    if not isinstance(plan.get("group_by"), list) or not plan.get("group_by"):
        issues.append("group_by must identify the requested entity grain")
    if not isinstance(plan.get("null_policy"), str) or not plan.get("null_policy", "").strip():
        issues.append("null_policy is required")

    return issues


def _normalise_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def _condition_present(sql: str, condition: str) -> bool:
    match = re.fullmatch(r"([a-zA-Z_][\w]*)\s*(=|<>|>=|<=|>|<)\s*(.+)", condition.strip())
    if not match:
        return _normalise_sql(condition) in _normalise_sql(sql)
    column, operator, value = match.groups()
    pattern = rf"(?:\b[a-zA-Z_]\w*\.)?{re.escape(column)}\s*{re.escape(operator)}\s*{re.escape(value.strip())}"
    return re.search(pattern, sql, flags=re.IGNORECASE) is not None


def _join_has_keys(sql: str, left: str, right: str, keys: tuple[str, ...]) -> bool:
    return all(
        re.search(
            rf"(?:\b[a-zA-Z_]\w*\.)?\b{re.escape(left)}_{key}\b\s*=\s*"
            rf"(?:\b[a-zA-Z_]\w*\.)?\b{re.escape(right)}_{key}\b|"
            rf"(?:\b[a-zA-Z_]\w*\.)?\b{re.escape(right)}_{key}\b\s*=\s*"
            rf"(?:\b[a-zA-Z_]\w*\.)?\b{re.escape(left)}_{key}\b",
            sql,
            flags=re.IGNORECASE,
        )
        is not None
        for key in keys
    )


def validate_sql(sql: str, plan: Mapping[str, Any]) -> list[str]:
    """Return deterministic violations for SQL generated from a Query Plan."""

    issues: list[str] = []
    normalised = _normalise_sql(sql)
    if not re.match(r"^(select|with)\b", normalised):
        issues.append("SQL must be a SELECT or WITH query")
    if "<sup" in normalised or "<br" in normalised:
        issues.append("SQL must not contain HTML")
    if "getdate(" in normalised or "current_date" in normalised:
        issues.append("SQL must not replace an explicit date with a dynamic date")

    metric = str(plan.get("metric", "")).lower()
    if "count_distinct(smdob_docno)" in metric and not re.search(
        r"count\s*\(\s*distinct\s+(?:\w+\.)?smdob_docno\s*\)", sql, flags=re.IGNORECASE
    ):
        issues.append("SQL metric must count distinct smdob_docno")

    for condition in plan.get("filters", []):
        if isinstance(condition, str) and not _condition_present(sql, condition):
            issues.append(f"Missing required filter: {condition}")

    date_range = plan.get("date_range")
    if isinstance(date_range, dict):
        column = str(date_range.get("column", ""))
        start = str(date_range.get("start", ""))
        end = str(date_range.get("end", ""))
        unbounded = all(
            value.strip().casefold() in {"", "none", "null", "n/a", "na", "not applicable"}
            for value in (column, start, end)
        )
        if not unbounded and column and start and not re.search(
            rf"(?:\b\w+\.)?{re.escape(column)}\s*>=\s*['\"]?{re.escape(start)}",
            sql,
            flags=re.IGNORECASE,
        ):
            issues.append(f"Missing explicit start date for {column}: {start}")
        if not unbounded and column and end and not re.search(
            rf"(?:\b\w+\.)?{re.escape(column)}\s*<\s*['\"]?{re.escape(end)}",
            sql,
            flags=re.IGNORECASE,
        ):
            issues.append(f"Missing explicit end date for {column}: {end}")

    for entity in plan.get("group_by", []):
        if isinstance(entity, str) and not re.search(
            rf"\b{re.escape(entity.split('.')[-1])}\b", sql, flags=re.IGNORECASE
        ):
            issues.append(f"SQL does not contain planned grouping field: {entity}")

    for join in plan.get("joins", []):
        if not isinstance(join, dict):
            continue
        table = str(join.get("table", "")).lower()
        if not table:
            continue
        if not re.search(
            rf"\[heran\]\s*\.\s*\[dbo\]\s*\.\s*\[{re.escape(table)}\]",
            sql,
            flags=re.IGNORECASE,
        ):
            issues.append(f"SQL must use verified three-part table name for {table}")
        if table == "smdoa" and not _join_has_keys(sql, "smdoa", "smdob", ("ent", "site", "docno")):
            issues.append("Join smdoa/smdob must include complete ent/site/docno keys")
        if table == "wmmta":
            if not re.search(r"\bleft\s+join\s+\[heran\]\s*\.\s*\[dbo\]\s*\.\s*\[wmmta\]", sql, flags=re.IGNORECASE):
                issues.append("Descriptive wmmta join must use LEFT JOIN")
            if not _join_has_keys(sql, "wmmta", "smdob", ("ent", "site", "itemno")):
                issues.append("Join wmmta/smdob must include complete ent/site/itemno keys")

    return issues


def _execution_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"ok": False, "message": value}
        if isinstance(parsed, Mapping):
            return parsed
    return {"ok": False, "message": "SQL executor returned an unsupported result"}


def run_sql_workflow(
    question: str,
    *,
    knowledge: str,
    plan_agent: Any,
    sql_agent: Any,
    repair_agent: Any,
    execute_sql: Any,
    max_repair_attempts: int = 2,
    on_stage: Any = None,
) -> SqlWorkflowResult:
    """Run the deterministic Plan -> SQL -> validate -> repair -> execute flow."""

    def emit_stage(stage: str, status: str, **details: Any) -> None:
        if on_stage is None:
            return
        event = {"stage": stage, "status": status}
        event.update(details)
        on_stage(event)

    emit_stage("planning", "started")
    plan = normalise_query_plan(parse_query_plan(plan_agent(question, knowledge)))
    plan_issues = validate_query_plan(plan)
    if plan_issues:
        emit_stage("planning", "failed", issue_count=len(plan_issues))
        raise QueryPlanValidationError("; ".join(plan_issues))
    emit_stage("planning", "completed")

    emit_stage("sql_generation", "started")
    sql = _clean_sql_candidate(sql_agent(question, plan, knowledge))
    emit_stage("sql_generation", "completed")
    repair_attempts = 0

    while True:
        sql_issues = validate_sql(sql, plan)
        if sql_issues:
            emit_stage("validation", "failed", issue_count=len(sql_issues))
            if repair_attempts >= max_repair_attempts:
                emit_stage("repair", "failed", attempt=repair_attempts + 1)
                raise SqlWorkflowError("SQL validation failed: " + "; ".join(sql_issues))
            repair_attempts += 1
            emit_stage("repair", "started", attempt=repair_attempts)
            sql = _clean_sql_candidate(repair_agent(sql, plan, sql_issues, knowledge))
            emit_stage("repair", "completed", attempt=repair_attempts)
            continue

        emit_stage("validation", "passed")
        emit_stage("execution", "started")
        execution = _execution_mapping(execute_sql(sql))
        if execution.get("ok") is True:
            emit_stage("execution", "completed")
            emit_stage("result_validation", "completed")
            return SqlWorkflowResult(plan, sql, execution, repair_attempts)

        error_message = str(
            execution.get("message")
            or execution.get("error")
            or "SQL execution failed"
        )
        emit_stage("execution", "failed")
        if repair_attempts >= max_repair_attempts:
            emit_stage("repair", "failed", attempt=repair_attempts + 1)
            raise SqlWorkflowError("SQL execution failed: " + error_message)
        repair_attempts += 1
        emit_stage("repair", "started", attempt=repair_attempts)
        sql = _clean_sql_candidate(
            repair_agent(
                sql,
                plan,
                [f"SQL execution failed: {error_message}"],
                knowledge,
            )
        )
        emit_stage("repair", "completed", attempt=repair_attempts)
