"""Discovery tools: `read_planning_state` (T15), the `manage_*` writers
(T16), `ask_user` (T17) (DESIGN.md §2.8, S5.4).

`read_planning_state(scope, project, **kwargs)` is a thin wrapper — every
scope below delegates entirely to an engine already built in Phase A. No
scope computes anything itself; if a scope's answer ever looks wrong, the
bug is in the engine it calls, not here.

Two guard rails, both load-bearing:

- `scope="entity"` **requires** a filter (`entity_id`, `entity_type`, or
  `status`) and caps its result count at `_MAX_ENTITY_RESULTS` — it must be
  structurally impossible to get the whole ledger back from this scope.
  That is what `scope="digest"` is for.
- `scope="readiness"` returns the blocker list, not just a boolean — the
  agent needs to be able to explain itself, not just report pass/fail.

Results are always data (dicts built from `model_dump(mode="json")`),
never prose — narration is the model's job, at the point of use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from pydantic import ValidationError

from ppa.config.areas import AREA_KEYS
from ppa.engines.coverage import compute_coverage, progress
from ppa.engines.dates import expected_decision_date
from ppa.engines.impact import analyze_impact
from ppa.engines.open_items import collect_open_items
from ppa.engines.readiness import check_readiness
from ppa.ledger.audit import AuditResult, record_audit
from ppa.ledger.digest import generate_digest
from ppa.ledger.events import EventType
from ppa.ledger.materialize import current_entities, entity_type_for, rebuild_all
from ppa.ledger.models import Assumption, BaseEntity, Decision, EntityType, HistoryEntry, Requirement, Unknown
from ppa.ledger.project import DEFAULT_PROJECTS_ROOT, Project, open_project
from ppa.ledger.secrets import scan_and_redact
from ppa.ledger.store import append_event_with_id, ledger_version
from ppa.ledger.transitions import IllegalTransition, validate_transition
from ppa.results.categories import CATEGORY_RULES, ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult
from ppa.tools.registry import register
from ppa.tools.spec import ToolSpec

_MAX_ENTITY_RESULTS = 20

Entities = Mapping[str, BaseEntity]
ScopeHandler = Callable[[Project, Entities], ToolResult]


def _validation_error(scope: str, message: str) -> ToolResult:
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.VALIDATION,
            code="MISSING_FILTER",
            is_retryable=False,
            description=f"scope={scope!r}: {message}",
            recommended_action=RecoveryAction.CORRECT_AND_RETRY,
        ),
    )


def _business_error(scope: str, message: str) -> ToolResult:
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.BUSINESS,
            code="NOT_FOUND",
            is_retryable=False,
            description=f"scope={scope!r}: {message}",
            recommended_action=RecoveryAction.CHANGE_WORKFLOW,
        ),
    )


def _digest_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    text = generate_digest(
        project, entities, coverage=kwargs.get("coverage"), round_number=kwargs.get("round_number")
    )
    return ToolResult(success=True, result_count=1, data={"digest": text})


def _matches_filters(eid: str, e: BaseEntity, entity_type: str | None, status: str | None) -> bool:
    return (not entity_type or entity_type_for(eid).value == entity_type) and (not status or e.status == status)


def _entity_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    entity_id = kwargs.get("entity_id")
    entity_type = kwargs.get("entity_type")
    status = kwargs.get("status")
    if not entity_id and not entity_type and not status:
        return _validation_error("entity", "requires entity_id, entity_type, or status")

    if entity_id:
        entity = entities.get(entity_id)
        data = [entity.model_dump(mode="json")] if entity else []
        return ToolResult(success=True, result_count=len(data), data=data)

    matches = [e for eid, e in entities.items() if _matches_filters(eid, e, entity_type, status)]
    limit = min(int(kwargs.get("limit", _MAX_ENTITY_RESULTS)), _MAX_ENTITY_RESULTS)
    page = matches[:limit]
    data = [e.model_dump(mode="json") for e in page]
    return ToolResult(success=True, degraded=len(matches) > limit, result_count=len(page), data=data)


def _history_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    entity_id = kwargs.get("entity_id")
    if not entity_id:
        return _validation_error("history", "requires entity_id")
    entity = entities.get(entity_id)
    if entity is None:
        return _business_error("history", f"no such entity: {entity_id}")
    history = [h.model_dump(mode="json") for h in entity.history]
    return ToolResult(success=True, result_count=len(history), data=history)


def _coverage_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    confirmed = kwargs.get("confirmed_areas")
    coverage = compute_coverage(entities, project.profile, confirmed_areas=confirmed)
    n_sufficient, n_critical = progress(entities, project.profile, confirmed_areas=confirmed)
    data = {
        "coverage": {area: state.value for area, state in coverage.items()},
        "critical_sufficient": n_sufficient,
        "critical_total": n_critical,
    }
    return ToolResult(success=True, result_count=len(coverage), data=data)


def _open_items_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    items = collect_open_items(entities)
    data = [item.model_dump(mode="json") for item in items]
    return ToolResult(success=True, result_count=len(data), data=data)


def _readiness_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    ready, blockers = check_readiness(
        entities,
        project.profile,
        confirmed_areas=kwargs.get("confirmed_areas"),
        unresolved_conflicts=kwargs.get("unresolved_conflicts"),
        review_approved=kwargs.get("review_approved", False),
    )
    data = {"ready": ready, "blockers": [b.model_dump(mode="json") for b in blockers]}
    return ToolResult(success=True, result_count=len(blockers), data=data)


def _impact_scope(project: Project, entities: Entities, **kwargs: Any) -> ToolResult:
    entity_id = kwargs.get("entity_id")
    if not entity_id:
        return _validation_error("impact", "requires entity_id")
    if entity_id not in entities:
        return _business_error("impact", f"no such entity: {entity_id}")
    report = analyze_impact(entity_id, entities)
    return ToolResult(success=True, result_count=len(report.affected), data=report.model_dump(mode="json"))


_SCOPES: dict[str, ScopeHandler] = {
    "digest": _digest_scope,
    "entity": _entity_scope,
    "history": _history_scope,
    "coverage": _coverage_scope,
    "open_items": _open_items_scope,
    "readiness": _readiness_scope,
    "impact": _impact_scope,
}


def read_planning_state(scope: str, project: Project, **kwargs: Any) -> ToolResult:
    """Route to the engine for `scope`, on a fresh read of `project`'s
    current entity state. No logic beyond routing lives here — see the
    module docstring."""

    handler = _SCOPES.get(scope)
    if handler is None:
        return _validation_error(scope, f"unknown scope — must be one of {sorted(_SCOPES)}")
    entities = current_entities(project.events_path)
    return handler(project, entities, **kwargs)


async def _read_planning_state_handler(args: dict[str, Any]) -> dict[str, Any]:
    """The SDK-facing adapter: MCP tool arguments are a flat JSON-able dict,
    so `project` is resolved here from `project_slug` before delegating to
    the real, directly-testable `read_planning_state` above."""

    scope = args.get("scope", "")
    project_slug = args.get("project_slug")
    if not project_slug:
        result = _validation_error(scope, "requires project_slug")
    else:
        projects_root = args.get("projects_root", DEFAULT_PROJECTS_ROOT)
        project = open_project(project_slug, projects_root=projects_root)
        kwargs = {k: v for k, v in args.items() if k not in ("scope", "project_slug", "projects_root")}
        result = read_planning_state(scope, project, **kwargs)

    return {
        "content": [{"type": "text", "text": result.model_dump_json()}],
        "is_error": not result.success,
    }


READ_PLANNING_STATE_SPEC = ToolSpec(
    name="read_planning_state",
    purpose=(
        "The one consolidated reader for ledger state: digest, entity lookups, version "
        "history, coverage, open items, the readiness gate, and impact traversal. Never "
        "writes anything."
    ),
    inputs={
        "scope": "str, one of digest|entity|history|coverage|open_items|readiness|impact",
        "project_slug": "str, the project's slug, as returned by create_project/list_projects",
        "entity_id": "str, an entity id — required for history and impact, one of the filters for entity",
        "entity_type": "str, an entity type name — a filter for scope=entity",
        "status": "str, a status value — a filter for scope=entity",
        "limit": "int, max rows for scope=entity, capped at 20 regardless of the value passed",
    },
    required=["scope", "project_slug"],
    optional=["entity_id", "entity_type", "status", "limit"],
    formats={
        "scope": "one of: digest, entity, history, coverage, open_items, readiness, impact",
        "limit": "1-20",
    },
    returns="A ToolResult whose `data` shape depends on `scope` — see examples.",
    examples=[
        'read_planning_state(scope="digest", project_slug="invoice-tracker")',
        'read_planning_state(scope="entity", project_slug="invoice-tracker", entity_id="REQ-001")',
        'read_planning_state(scope="readiness", project_slug="invoice-tracker")',
    ],
    edge_cases=[
        "scope=entity with no filter at all returns VALIDATION, never the whole ledger",
        "scope=history for an entity with no recorded changes returns an empty list, not an error",
    ],
    limitations=[
        "scope=entity never returns more than 20 rows per call, even when more match — page with status/entity_type filters instead",
        "read-only: never creates, revises, confirms, or deletes anything",
    ],
    use_when=[
        "the agent needs current ledger state before deciding what to ask or write next",
        "the agent needs to explain a readiness-gate failure to the user, by entity and reason",
    ],
    do_not_use_when=[
        "the agent wants to create or change an entity -> use the matching manage_* tool instead",
        "the agent wants to record a user's answer -> use manage_* tools, not this one",
    ],
    related_tools={
        "manage_requirement": "writes Requirement entities; this tool never writes anything",
        "manage_assumption": "writes Assumption entities; this tool never writes anything",
    },
)

register(
    READ_PLANNING_STATE_SPEC,
    _read_planning_state_handler,
    owner_agents=["discovery", "guidance", "research", "planning", "delivery"],
)


# ---------------------------------------------------------------------------
# The manage_* writers (T16, DESIGN.md S5.5).
#
# Four parameterized writers, each `operation`-dispatched rather than split
# into one tool per verb — see the module docstring's own worked example in
# `t16_manage_writer_tools.md` for why. Every write here runs the same six
# steps that file lays out: schema -> workflow -> semantic -> consistency ->
# secret-scan -> append/materialize/audit. Permission (layer 1) is not this
# module's job — that is `ppa/tools/dispatch.py` (T14), checked before this
# module's handler ever runs.
#
# `_generic_transition` is the one function every non-`create`/`open`/
# `record` operation across all four entity types goes through — status
# changes, field edits and history all follow the same shape, so a
# revise/confirm/reject/modify/defer/decide/classify/resolve/convert bug
# gets fixed once, not four or eight times.
#
# **Audit is self-recorded here**, not left to the dispatcher: `ppa/tools/
# dispatch.py` still wraps every handler call as `success=True`
# unconditionally (T14's own docstring: T19 fixes that), so a caller that
# routed a rejected write through `dispatch()` today would get a false
# success. T19 (validation layer wiring) is where this gets reconciled —
# either the dispatcher starts trusting the handler's real result and this
# module's self-audit is removed in favor of a single dispatcher-side audit
# point, or the dispatcher's write-path audit is dropped in favor of this
# one. Tracked as decision #24 in `blockers.md` rather than guessed at
# silently here.
# ---------------------------------------------------------------------------


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _missing_fields(kwargs: Mapping[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [f for f in fields if f not in kwargs or _is_blank(kwargs[f])]


def _error(category: ErrorCategory, code: str, description: str, context: dict[str, Any] | None = None) -> ToolResult:
    rule = CATEGORY_RULES[category]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=category,
            code=code,
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=description,
            context=context or {},
        ),
    )


def _validate_new_entity(model_cls: type[BaseEntity], after: dict[str, Any], id_prefix: str) -> ValidationError | None:
    """Schema-check a not-yet-written entity dict without tripping the `id`
    validator on the `"PENDING"` placeholder every `_*_create`/`_decision_
    open`/`_unknown_record` function uses — `append_event_with_id` is what
    actually replaces `"PENDING"` with a real allocated id, after this check
    runs. A dummy id of the right shape is substituted for validation only;
    the real `after` dict handed to the event still carries `"PENDING"`."""

    probe = dict(after, id=f"{id_prefix}-000")
    try:
        model_cls.model_validate(probe)
        return None
    except ValidationError as exc:
        return exc


def _dangling_refs(entities: Mapping[str, BaseEntity], ids: list[str], expected_type: EntityType) -> list[str]:
    bad: list[str] = []
    for eid in ids:
        try:
            actual_type = entity_type_for(eid)
        except ValueError:
            bad.append(eid)
            continue
        if actual_type is not expected_type or eid not in entities:
            bad.append(eid)
    return bad


def _open_blocking_unknowns_for_areas(entities: Mapping[str, BaseEntity], areas: list[str]) -> list[str]:
    areas_set = set(areas)
    return [
        eid
        for eid, e in entities.items()
        if entity_type_for(eid) is EntityType.UNKNOWN
        and e.blocking
        and e.status == "OPEN"
        and e.area in areas_set
    ]


def _audit_write(
    project: Project,
    *,
    agent_id: str,
    tool: str,
    workflow_state: str,
    args: dict[str, Any],
    reason: str,
    result: ToolResult,
    ledger_version_before: int,
    ledger_version_after: int,
    entity_id: str | None = None,
) -> None:
    error = result.error
    record_audit(
        agent=agent_id,
        tool=tool,
        operation="write" if result.success else "reject",
        workflow_state=workflow_state,
        inputs=args,
        reason=reason,
        result=AuditResult(
            success=result.success,
            category=error.category if error else None,
            code=error.code if error else None,
        ),
        path=project.audit_path,
        entity_id=entity_id,
        ledger_version_before=ledger_version_before,
        ledger_version_after=ledger_version_after,
    )


def _reject_write(
    project: Project,
    *,
    tool: str,
    agent_id: str,
    workflow_state: str,
    args: dict[str, Any],
    reason: str,
    result: ToolResult,
) -> ToolResult:
    version = ledger_version(project.events_path)
    _audit_write(
        project,
        agent_id=agent_id,
        tool=tool,
        workflow_state=workflow_state,
        args=args,
        reason=reason,
        result=result,
        ledger_version_before=version,
        ledger_version_after=version,
    )
    return result


def _commit_write(
    project: Project,
    *,
    tool: str,
    agent_id: str,
    workflow_state: str,
    fields: dict[str, Any],
    args: dict[str, Any],
    reason: str,
    id_prefix: str | None = None,
    idem_key: str | None = None,
) -> ToolResult:
    version_before = ledger_version(project.events_path)
    write_result = append_event_with_id(fields, project.events_path, id_prefix=id_prefix, idem_key=idem_key)
    rebuild_all(project.events_path)
    version_after = ledger_version(project.events_path)
    result = ToolResult(
        success=True,
        result_count=1,
        data={
            "entity_id": write_result.entity_id,
            "event_id": write_result.event_id,
            "replayed": write_result.replayed,
        },
    )
    _audit_write(
        project,
        agent_id=agent_id,
        tool=tool,
        workflow_state=workflow_state,
        args=args,
        reason=reason,
        result=result,
        ledger_version_before=version_before,
        ledger_version_after=version_after,
        entity_id=write_result.entity_id,
    )
    return result


def _get_entity_or_error(
    project: Project,
    entity_id: str | None,
    expected_type: EntityType,
    tool: str,
    agent_id: str,
    workflow_state: str,
    args: dict[str, Any],
) -> tuple[dict[str, BaseEntity] | None, BaseEntity | None, ToolResult | None]:
    if not entity_id:
        result = _error(ErrorCategory.VALIDATION, "MISSING_ENTITY_ID", f"{tool}: requires entity_id")
        return None, None, _reject_write(
            project, tool=tool, agent_id=agent_id, workflow_state=workflow_state,
            args=args, reason="missing entity_id", result=result,
        )

    entities = current_entities(project.events_path)
    entity = entities.get(entity_id)
    try:
        actual_type = entity_type_for(entity_id)
    except ValueError:
        actual_type = None
    if entity is None or actual_type is not expected_type:
        result = _error(
            ErrorCategory.BUSINESS, "NOT_FOUND", f"{tool}: no such {expected_type.value} entity_id={entity_id!r}",
        )
        return None, None, _reject_write(
            project, tool=tool, agent_id=agent_id, workflow_state=workflow_state,
            args=args, reason=f"no such entity {entity_id}", result=result,
        )

    return entities, entity, None


@dataclass(frozen=True)
class _OpConfig:
    """One row of an entity type's operation table — everything
    `_generic_transition` needs to run a non-create status/field change
    uniformly across all four `manage_*` tools."""

    event_type: EventType
    new_status: str | None = None
    required: tuple[str, ...] = ()
    require_any_of: tuple[str, ...] | None = None
    updatable: tuple[str, ...] = ()
    scan_fields: tuple[str, ...] = ()
    allowed_from: tuple[str, ...] | None = None


SemanticCheck = Callable[[Mapping[str, BaseEntity], BaseEntity, dict[str, Any]], ToolResult | None]
ExtraApply = Callable[[dict[str, Any], dict[str, Any], datetime, str], None]


def _generic_transition(
    operation: str,
    entity_type: EntityType,
    model_cls: type[BaseEntity],
    config: _OpConfig,
    project: Project,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str,
    agent_id: str,
    actor_role: str,
    now: datetime,
    idem_key: str | None,
    args: dict[str, Any],
    kwargs: dict[str, Any],
    tool: str,
    semantic_check: SemanticCheck | None = None,
    extra_apply: ExtraApply | None = None,
) -> ToolResult:
    entity_id = kwargs.get("entity_id")
    entities, entity, error = _get_entity_or_error(project, entity_id, entity_type, tool, agent_id, workflow_state, args)
    if error is not None:
        return error

    if config.allowed_from is not None and entity.status not in config.allowed_from:
        result = _error(
            ErrorCategory.BUSINESS, "ILLEGAL_TRANSITION",
            f"{tool}({operation}) rejected: {entity_id} is {entity.status}, must be one of {config.allowed_from}",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="status guard failed", result=result)

    missing = _missing_fields(kwargs, config.required)
    if missing:
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_REQUIRED_FIELD",
            f"{tool}({operation}) requires {', '.join(config.required)}. Missing: {', '.join(missing)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="missing required field(s)", result=result)

    if config.require_any_of is not None and not any(kwargs.get(f) for f in config.require_any_of):
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_ANY_OF",
            f"{tool}({operation}) requires at least one of {', '.join(config.require_any_of)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="no fields to update", result=result)

    new_status = config.new_status or entity.status
    try:
        validate_transition(entity_type, entity.status, new_status)
    except IllegalTransition as exc:
        result = _error(ErrorCategory.BUSINESS, "ILLEGAL_TRANSITION", f"{tool}({operation}): {exc}")
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason=str(exc), result=result)

    if semantic_check is not None:
        semantic_error = semantic_check(entities, entity, kwargs)
        if semantic_error is not None:
            return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="semantic check failed", result=semantic_error)

    before = entity.model_dump(mode="json")
    updated = dict(before)
    history = list(before["history"])
    change_reason = kwargs.get("change_reason") or f"{operation} via {tool}"

    for field in config.updatable:
        if field in kwargs:
            new_value = kwargs[field]
            if field in config.scan_fields and isinstance(new_value, str):
                new_value, _findings = scan_and_redact(new_value)
            old_value = updated.get(field)
            if new_value != old_value:
                history.append(
                    HistoryEntry(
                        field=field, old_value=old_value, new_value=new_value,
                        changed_at=now, changed_by=actor_id, reason=change_reason,
                    ).model_dump(mode="json")
                )
                updated[field] = new_value

    if config.new_status is not None and new_status != entity.status:
        history.append(
            HistoryEntry(
                field="status", old_value=entity.status, new_value=new_status,
                changed_at=now, changed_by=actor_id, reason=change_reason,
            ).model_dump(mode="json")
        )
        updated["status"] = new_status

    if extra_apply is not None:
        extra_apply(updated, kwargs, now, actor_id)

    updated["version"] = entity.version + 1
    updated["updated_at"] = now.isoformat()
    updated["updated_by"] = actor_id
    updated["history"] = history

    try:
        model_cls.model_validate(updated)
    except ValidationError as exc:
        result = _error(ErrorCategory.VALIDATION, "SCHEMA_INVALID", f"{tool}({operation}): {exc}")
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="schema validation failed", result=result)

    fields = dict(
        ts=now, type=config.event_type, entity_id=entity_id, actor_id=actor_id, actor_role=actor_role,
        agent_name=None if actor_role == "user" else agent_id, workflow_state=workflow_state, txn_id=None,
        source=tool, reason=change_reason, before=before, after=updated, session_id=session_id,
    )
    return _commit_write(
        project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, fields=fields,
        args=args, reason=change_reason, idem_key=idem_key,
    )


# --- manage_requirement -----------------------------------------------------

_REQUIREMENT_CREATE_REQUIRED = ("statement", "type", "priority", "confidence", "confidence_basis")
_REQUIREMENT_PROVENANCE_FIELDS = ("derived_from_answers", "depends_on_assumptions", "depends_on_decisions")
_REQUIREMENT_MUTABLE_FIELDS = (
    "statement", "type", "covers_areas", "priority", "confidence", "confidence_basis",
    "needs_user_confirmation", "custom_fields",
    "derived_from_answers", "depends_on_assumptions", "depends_on_decisions",
)


def _requirement_create(
    project: Project, *, actor_id: str, session_id: str, workflow_state: str, agent_id: str,
    actor_role: str, now: datetime, idem_key: str | None, args: dict[str, Any], kwargs: dict[str, Any],
) -> ToolResult:
    tool = "manage_requirement"
    missing = _missing_fields(kwargs, _REQUIREMENT_CREATE_REQUIRED)
    if missing:
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_REQUIRED_FIELD",
            f"{tool}(create) requires {', '.join(_REQUIREMENT_CREATE_REQUIRED)}. Missing: {', '.join(missing)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="missing required field(s)", result=result)

    covers_areas = list(kwargs.get("covers_areas") or [])
    invalid_areas = [a for a in covers_areas if a not in AREA_KEYS]
    if not covers_areas or invalid_areas:
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_COVERS_AREAS",
            f"{tool}(create) requires covers_areas (non-empty list of area keys from config/areas.py). "
            f"Received: {covers_areas!r}. Valid keys: {', '.join(AREA_KEYS)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="covers_areas missing or invalid", result=result)

    if not any(kwargs.get(f) for f in _REQUIREMENT_PROVENANCE_FIELDS):
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_PROVENANCE",
            f"{tool}(create) requires at least one of {', '.join(_REQUIREMENT_PROVENANCE_FIELDS)} "
            "(non-empty) — a requirement must trace to an answer, an assumption or a decision.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="no provenance link", result=result)

    entities = current_entities(project.events_path)
    for field, expected_type in (
        ("derived_from_answers", EntityType.QUESTION_ANSWER),
        ("depends_on_assumptions", EntityType.ASSUMPTION),
        ("depends_on_decisions", EntityType.DECISION),
    ):
        bad = _dangling_refs(entities, list(kwargs.get(field) or []), expected_type)
        if bad:
            result = _error(
                ErrorCategory.BUSINESS, "DANGLING_REFERENCE",
                f"{tool}(create): {field} references entities that do not exist: {bad}",
            )
            return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason=f"dangling reference in {field}", result=result)

    statement, _findings = scan_and_redact(kwargs["statement"])
    confidence_basis, _findings = scan_and_redact(kwargs["confidence_basis"])

    after = dict(
        id="PENDING", version=1, created_at=now.isoformat(), updated_at=now.isoformat(),
        created_by=actor_id, updated_by=actor_id, history=[],
        confidence=kwargs["confidence"], confidence_basis=confidence_basis,
        status="PROPOSED", statement=statement, type=kwargs["type"], covers_areas=covers_areas,
        derived_from_answers=list(kwargs.get("derived_from_answers") or []),
        depends_on_assumptions=list(kwargs.get("depends_on_assumptions") or []),
        depends_on_decisions=list(kwargs.get("depends_on_decisions") or []),
        priority=kwargs["priority"], needs_user_confirmation=kwargs.get("needs_user_confirmation", False),
        custom_fields=dict(kwargs.get("custom_fields") or {}),
    )

    exc = _validate_new_entity(Requirement, after, "REQ")
    if exc is not None:
        result = _error(ErrorCategory.VALIDATION, "SCHEMA_INVALID", f"{tool}(create): {exc}")
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="schema validation failed", result=result)

    fields = dict(
        ts=now, type=EventType.REQUIREMENT_CREATED, entity_id=None, actor_id=actor_id, actor_role=actor_role,
        agent_name=None if actor_role == "user" else agent_id, workflow_state=workflow_state, txn_id=None,
        source=tool, reason=kwargs.get("change_reason", "requirement created"), before=None, after=after, session_id=session_id,
    )
    return _commit_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, fields=fields, args=args, reason="requirement created", id_prefix="REQ", idem_key=idem_key)


def _requirement_confirm_semantic_check(entities: Mapping[str, BaseEntity], entity: BaseEntity, kwargs: dict[str, Any]) -> ToolResult | None:
    blockers = _open_blocking_unknowns_for_areas(entities, entity.covers_areas)
    if blockers:
        return _error(
            ErrorCategory.BUSINESS, "AREA_BLOCKED",
            f"manage_requirement(confirm) rejected: covers_areas {entity.covers_areas} has open blocking "
            f"unknown(s): {blockers} — resolve or convert them before confirming",
            context={"blocking_unknowns": blockers},
        )
    return None


_REQUIREMENT_OPS: dict[str, _OpConfig] = {
    "revise": _OpConfig(
        event_type=EventType.REQUIREMENT_REVISED,
        updatable=_REQUIREMENT_MUTABLE_FIELDS,
        scan_fields=("statement", "confidence_basis"),
        allowed_from=("PROPOSED",),
    ),
    "confirm": _OpConfig(event_type=EventType.REQUIREMENT_CONFIRMED, new_status="CONFIRMED"),
    "reject": _OpConfig(event_type=EventType.REQUIREMENT_REJECTED, new_status="REJECTED"),
    "supersede": _OpConfig(event_type=EventType.REQUIREMENT_SUPERSEDED, new_status="SUPERSEDED"),
}


def manage_requirement(
    operation: str,
    project: Project,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    agent_id: str = "discovery",
    actor_role: str = "agent",
    now: datetime | None = None,
    idem_key: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    """`create | revise | confirm | reject | supersede`. `create` requires
    `covers_areas` and at least one provenance link — see the module's own
    T16 section docstring."""

    tool = "manage_requirement"
    ts = _now(now)
    args = {"operation": operation, **kwargs}

    if operation == "create":
        return _requirement_create(
            project, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state,
            agent_id=agent_id, actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs,
        )

    config = _REQUIREMENT_OPS.get(operation)
    if config is None:
        result = _error(
            ErrorCategory.VALIDATION, "UNKNOWN_OPERATION",
            f"{tool}: unknown operation {operation!r} — must be one of create, revise, confirm, reject, supersede",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason=f"unknown operation {operation!r}", result=result)

    return _generic_transition(
        operation, EntityType.REQUIREMENT, Requirement, config, project,
        actor_id=actor_id, session_id=session_id, workflow_state=workflow_state, agent_id=agent_id,
        actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs, tool=tool,
        semantic_check=_requirement_confirm_semantic_check if operation == "confirm" else None,
    )


# --- manage_assumption -------------------------------------------------------

_ASSUMPTION_CREATE_REQUIRED = ("statement", "reason", "impact", "confidence", "confidence_basis")


def _assumption_create(
    project: Project, *, actor_id: str, session_id: str, workflow_state: str, agent_id: str,
    actor_role: str, now: datetime, idem_key: str | None, args: dict[str, Any], kwargs: dict[str, Any],
) -> ToolResult:
    tool = "manage_assumption"
    missing = _missing_fields(kwargs, _ASSUMPTION_CREATE_REQUIRED)
    if missing:
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_REQUIRED_FIELD",
            f"{tool}(create) requires {', '.join(_ASSUMPTION_CREATE_REQUIRED)}. Missing: {', '.join(missing)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="missing required field(s)", result=result)

    statement, _findings = scan_and_redact(kwargs["statement"])
    reason_text, _findings = scan_and_redact(kwargs["reason"])
    confidence_basis, _findings = scan_and_redact(kwargs["confidence_basis"])

    after = dict(
        id="PENDING", version=1, created_at=now.isoformat(), updated_at=now.isoformat(),
        created_by=actor_id, updated_by=actor_id, history=[],
        confidence=kwargs["confidence"], confidence_basis=confidence_basis,
        status="PROPOSED", statement=statement, reason=reason_text, impact=kwargs["impact"],
        affects_requirements=list(kwargs.get("affects_requirements") or []),
        affects_areas=list(kwargs.get("affects_areas") or []),
        user_confirmation_required=kwargs.get("user_confirmation_required", False),
        confirmed_at=None, confirmed_by=None, provisional=kwargs.get("provisional", False),
    )

    exc = _validate_new_entity(Assumption, after, "ASM")
    if exc is not None:
        result = _error(ErrorCategory.VALIDATION, "SCHEMA_INVALID", f"{tool}(create): {exc}")
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="schema validation failed", result=result)

    fields = dict(
        ts=now, type=EventType.ASSUMPTION_CREATED, entity_id=None, actor_id=actor_id, actor_role=actor_role,
        agent_name=None if actor_role == "user" else agent_id, workflow_state=workflow_state, txn_id=None,
        source=tool, reason=kwargs.get("change_reason", "assumption created"), before=None, after=after, session_id=session_id,
    )
    return _commit_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, fields=fields, args=args, reason="assumption created", id_prefix="ASM", idem_key=idem_key)


def _assumption_confirm_extra(updated: dict[str, Any], kwargs: dict[str, Any], now: datetime, actor_id: str) -> None:
    updated["confirmed_at"] = now.isoformat()
    updated["confirmed_by"] = actor_id


_ASSUMPTION_OPS: dict[str, _OpConfig] = {
    "confirm": _OpConfig(event_type=EventType.ASSUMPTION_CONFIRMED, new_status="CONFIRMED"),
    "reject": _OpConfig(event_type=EventType.ASSUMPTION_REJECTED, new_status="REJECTED"),
    "modify": _OpConfig(
        event_type=EventType.ASSUMPTION_MODIFIED,
        updatable=(
            "statement", "reason", "impact", "affects_requirements", "affects_areas",
            "confidence", "confidence_basis", "user_confirmation_required", "provisional",
        ),
        scan_fields=("statement", "reason", "confidence_basis"),
        allowed_from=("PROPOSED",),
    ),
    "supersede": _OpConfig(event_type=EventType.ASSUMPTION_SUPERSEDED, new_status="SUPERSEDED"),
}


def manage_assumption(
    operation: str,
    project: Project,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    agent_id: str = "discovery",
    actor_role: str = "agent",
    now: datetime | None = None,
    idem_key: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    """`create | confirm | reject | modify | supersede`."""

    tool = "manage_assumption"
    ts = _now(now)
    args = {"operation": operation, **kwargs}

    if operation == "create":
        return _assumption_create(
            project, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state,
            agent_id=agent_id, actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs,
        )

    config = _ASSUMPTION_OPS.get(operation)
    if config is None:
        result = _error(
            ErrorCategory.VALIDATION, "UNKNOWN_OPERATION",
            f"{tool}: unknown operation {operation!r} — must be one of create, confirm, reject, modify, supersede",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason=f"unknown operation {operation!r}", result=result)

    return _generic_transition(
        operation, EntityType.ASSUMPTION, Assumption, config, project,
        actor_id=actor_id, session_id=session_id, workflow_state=workflow_state, agent_id=agent_id,
        actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs, tool=tool,
        extra_apply=_assumption_confirm_extra if operation == "confirm" else None,
    )


# --- manage_decision ---------------------------------------------------------

_DECISION_OPEN_REQUIRED = ("question", "owner", "owner_type")


def _decision_open(
    project: Project, *, actor_id: str, session_id: str, workflow_state: str, agent_id: str,
    actor_role: str, now: datetime, idem_key: str | None, args: dict[str, Any], kwargs: dict[str, Any],
) -> ToolResult:
    tool = "manage_decision"
    missing = _missing_fields(kwargs, _DECISION_OPEN_REQUIRED)
    if missing:
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_REQUIRED_FIELD",
            f"{tool}(open) requires {', '.join(_DECISION_OPEN_REQUIRED)}. Missing: {', '.join(missing)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="missing required field(s)", result=result)

    question, _findings = scan_and_redact(kwargs["question"])

    after = dict(
        id="PENDING", version=1, created_at=now.isoformat(), updated_at=now.isoformat(),
        created_by=actor_id, updated_by=actor_id, history=[],
        status="OPEN", question=question, blocking=kwargs.get("blocking", False),
        affects=kwargs.get("affects"), owner=kwargs["owner"], owner_type=kwargs["owner_type"],
        identified_at=now.isoformat(), expected_decision_date=None, decided_at=None, defer_reason=None,
        options=list(kwargs.get("options") or []), chosen_option=None, rationale=None,
        prerequisites=list(kwargs.get("prerequisites") or []), current_assumption=kwargs.get("current_assumption"),
        related_requirements=list(kwargs.get("related_requirements") or []),
        related_research=list(kwargs.get("related_research") or []),
    )

    exc = _validate_new_entity(Decision, after, "DEC")
    if exc is not None:
        result = _error(ErrorCategory.VALIDATION, "SCHEMA_INVALID", f"{tool}(open): {exc}")
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="schema validation failed", result=result)

    fields = dict(
        ts=now, type=EventType.DECISION_OPENED, entity_id=None, actor_id=actor_id, actor_role=actor_role,
        agent_name=None if actor_role == "user" else agent_id, workflow_state=workflow_state, txn_id=None,
        source=tool, reason=kwargs.get("change_reason", "decision opened"), before=None, after=after, session_id=session_id,
    )
    return _commit_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, fields=fields, args=args, reason="decision opened", id_prefix="DEC", idem_key=idem_key)


class _DecisionLike:
    """Duck-typed stand-in for `ppa.engines.dates.expected_decision_date`,
    built from the entity dict mid-update — see decision #21 in
    `blockers.md` for why that function reads `.blocking`/`.affects` off a
    real object rather than taking them as keyword arguments."""

    def __init__(self, blocking: bool, affects: str | None) -> None:
        self.blocking = blocking
        self.affects = affects


def _decision_defer_extra(updated: dict[str, Any], kwargs: dict[str, Any], now: datetime, actor_id: str) -> None:
    decision_like = _DecisionLike(blocking=updated["blocking"], affects=updated.get("affects"))
    updated["expected_decision_date"] = expected_decision_date(decision_like, now).isoformat()


def _decision_decide_extra(updated: dict[str, Any], kwargs: dict[str, Any], now: datetime, actor_id: str) -> None:
    updated["decided_at"] = now.isoformat()


_DECISION_OPS: dict[str, _OpConfig] = {
    "defer": _OpConfig(
        event_type=EventType.DECISION_DEFERRED, new_status="DECIDE_LATER",
        required=("defer_reason", "owner", "owner_type"),
        updatable=("defer_reason", "owner", "owner_type", "affects"),
        scan_fields=("defer_reason",),
    ),
    "decide": _OpConfig(
        event_type=EventType.DECISION_DECIDED, new_status="DECIDED",
        required=("chosen_option", "rationale"),
        updatable=("chosen_option", "rationale"),
        scan_fields=("rationale",),
    ),
    "supersede": _OpConfig(event_type=EventType.DECISION_SUPERSEDED, new_status="SUPERSEDED"),
}

_DECISION_EXTRA_APPLY: dict[str, ExtraApply] = {
    "defer": _decision_defer_extra,
    "decide": _decision_decide_extra,
}


def manage_decision(
    operation: str,
    project: Project,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    agent_id: str = "discovery",
    actor_role: str = "agent",
    now: datetime | None = None,
    idem_key: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    """`open | defer | decide | supersede`. `defer` requires `defer_reason`,
    `owner` and `owner_type`; `expected_decision_date` is never caller-
    supplied — it is always computed from T12's rule (`ppa.engines.dates.
    expected_decision_date`) against the decision's own `blocking`/`affects`
    fields once this call's other updates are applied. See decision #24 in
    `blockers.md` for why this task's original Done-when wording ("without
    expected_decision_date is rejected") was corrected to name the fields a
    caller actually supplies."""

    tool = "manage_decision"
    ts = _now(now)
    args = {"operation": operation, **kwargs}

    if operation == "open":
        return _decision_open(
            project, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state,
            agent_id=agent_id, actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs,
        )

    config = _DECISION_OPS.get(operation)
    if config is None:
        result = _error(
            ErrorCategory.VALIDATION, "UNKNOWN_OPERATION",
            f"{tool}: unknown operation {operation!r} — must be one of open, defer, decide, supersede",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason=f"unknown operation {operation!r}", result=result)

    return _generic_transition(
        operation, EntityType.DECISION, Decision, config, project,
        actor_id=actor_id, session_id=session_id, workflow_state=workflow_state, agent_id=agent_id,
        actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs, tool=tool,
        extra_apply=_DECISION_EXTRA_APPLY.get(operation),
    )


# --- manage_unknown -----------------------------------------------------------

_UNKNOWN_RECORD_REQUIRED = ("question", "area", "why_it_matters", "owner_type", "route")


def _unknown_record(
    project: Project, *, actor_id: str, session_id: str, workflow_state: str, agent_id: str,
    actor_role: str, now: datetime, idem_key: str | None, args: dict[str, Any], kwargs: dict[str, Any],
) -> ToolResult:
    tool = "manage_unknown"
    missing = _missing_fields(kwargs, _UNKNOWN_RECORD_REQUIRED)
    if "blocking" not in kwargs:
        missing.append("blocking")
    if missing:
        result = _error(
            ErrorCategory.VALIDATION, "MISSING_REQUIRED_FIELD",
            f"{tool}(record) requires question, area, why_it_matters, owner_type, blocking and route. "
            f"Missing: {', '.join(missing)}.",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="missing required field(s)", result=result)

    question, _findings = scan_and_redact(kwargs["question"])
    why_it_matters, _findings = scan_and_redact(kwargs["why_it_matters"])

    after = dict(
        id="PENDING", version=1, created_at=now.isoformat(), updated_at=now.isoformat(),
        created_by=actor_id, updated_by=actor_id, history=[],
        status="OPEN", question=question, area=kwargs["area"], why_it_matters=why_it_matters,
        blocking=kwargs["blocking"], route=kwargs["route"], owner_type=kwargs["owner_type"], converted_to=None,
    )

    exc = _validate_new_entity(Unknown, after, "UNK")
    if exc is not None:
        result = _error(ErrorCategory.VALIDATION, "SCHEMA_INVALID", f"{tool}(record): {exc}")
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="schema validation failed", result=result)

    fields = dict(
        ts=now, type=EventType.UNKNOWN_RECORDED, entity_id=None, actor_id=actor_id, actor_role=actor_role,
        agent_name=None if actor_role == "user" else agent_id, workflow_state=workflow_state, txn_id=None,
        source=tool, reason=kwargs.get("change_reason", "unknown recorded"), before=None, after=after, session_id=session_id,
    )
    return _commit_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, fields=fields, args=args, reason="unknown recorded", id_prefix="UNK", idem_key=idem_key)


def _unknown_convert_semantic_check(entities: Mapping[str, BaseEntity], entity: BaseEntity, kwargs: dict[str, Any]) -> ToolResult | None:
    converted_to = kwargs.get("converted_to")
    if converted_to and converted_to not in entities:
        return _error(
            ErrorCategory.BUSINESS, "DANGLING_REFERENCE",
            f"manage_unknown(convert): converted_to {converted_to!r} does not exist",
        )
    return None


_UNKNOWN_OPS: dict[str, _OpConfig] = {
    "classify": _OpConfig(
        event_type=EventType.UNKNOWN_CLASSIFIED,
        require_any_of=("blocking", "route", "area", "why_it_matters"),
        updatable=("blocking", "route", "area", "why_it_matters"),
        allowed_from=("OPEN",),
    ),
    "resolve": _OpConfig(event_type=EventType.UNKNOWN_RESOLVED, new_status="RESOLVED"),
    "convert": _OpConfig(
        event_type=EventType.UNKNOWN_CONVERTED, new_status="CONVERTED",
        required=("converted_to",), updatable=("converted_to",),
    ),
}


def manage_unknown(
    operation: str,
    project: Project,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    agent_id: str = "discovery",
    actor_role: str = "agent",
    now: datetime | None = None,
    idem_key: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    """`record | classify | resolve | convert`. `record` requires both
    `blocking` and `route` — see the module's T16 section docstring."""

    tool = "manage_unknown"
    ts = _now(now)
    args = {"operation": operation, **kwargs}

    if operation == "record":
        return _unknown_record(
            project, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state,
            agent_id=agent_id, actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs,
        )

    config = _UNKNOWN_OPS.get(operation)
    if config is None:
        result = _error(
            ErrorCategory.VALIDATION, "UNKNOWN_OPERATION",
            f"{tool}: unknown operation {operation!r} — must be one of record, classify, resolve, convert",
        )
        return _reject_write(project, tool=tool, agent_id=agent_id, workflow_state=workflow_state, args=args, reason=f"unknown operation {operation!r}", result=result)

    return _generic_transition(
        operation, EntityType.UNKNOWN, Unknown, config, project,
        actor_id=actor_id, session_id=session_id, workflow_state=workflow_state, agent_id=agent_id,
        actor_role=actor_role, now=ts, idem_key=idem_key, args=args, kwargs=kwargs, tool=tool,
        semantic_check=_unknown_convert_semantic_check if operation == "convert" else None,
    )


# --- SDK-facing handlers and ToolSpecs --------------------------------------


def _writer_kwargs_from_args(args: dict[str, Any], extra: tuple[str, ...] = ()) -> dict[str, Any]:
    excluded = {"operation", "project_slug", "projects_root", "actor_id", "session_id", "workflow_state", "agent_id", "actor_role", "idem_key", *extra}
    return {k: v for k, v in args.items() if k not in excluded}


async def _manage_writer_handler(writer: Callable[..., ToolResult], tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    operation = args.get("operation", "")
    project_slug = args.get("project_slug")
    if not project_slug:
        result = _error(ErrorCategory.VALIDATION, "MISSING_PROJECT_SLUG", f"{tool_name}: requires project_slug")
    else:
        projects_root = args.get("projects_root", DEFAULT_PROJECTS_ROOT)
        project = open_project(project_slug, projects_root=projects_root)
        result = writer(
            operation,
            project,
            actor_id=args.get("actor_id", "agent:discovery"),
            session_id=args.get("session_id", "session-unknown"),
            workflow_state=args.get("workflow_state", "DISCOVERY"),
            agent_id=args.get("agent_id", "discovery"),
            actor_role=args.get("actor_role", "agent"),
            idem_key=args.get("idem_key"),
            **_writer_kwargs_from_args(args),
        )
    return {"content": [{"type": "text", "text": result.model_dump_json()}], "is_error": not result.success}


async def _manage_requirement_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _manage_writer_handler(manage_requirement, "manage_requirement", args)


async def _manage_assumption_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _manage_writer_handler(manage_assumption, "manage_assumption", args)


async def _manage_decision_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _manage_writer_handler(manage_decision, "manage_decision", args)


async def _manage_unknown_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _manage_writer_handler(manage_unknown, "manage_unknown", args)


MANAGE_REQUIREMENT_SPEC = ToolSpec(
    name="manage_requirement",
    purpose="Create or change the status of a Requirement — the only tool that ever writes REQ-nnn entities.",
    inputs={
        "operation": "str, one of create|revise|confirm|reject|supersede",
        "project_slug": "str, the project's slug",
        "entity_id": "str, REQ-nnn — required for revise/confirm/reject/supersede",
        "statement": "str, the requirement text — required for create",
        "type": "str, one of functional|non_functional|constraint — required for create",
        "priority": "str, one of must|should|could|wont_v1 — required for create",
        "confidence": "str, one of HIGH|MEDIUM|LOW — required for create",
        "confidence_basis": "str, non-empty justification for confidence — required for create",
        "covers_areas": "list[str], area keys from config/areas.py — required non-empty for create",
        "derived_from_answers": "list[str], ANS-nnn ids — provenance link (one of three required for create)",
        "depends_on_assumptions": "list[str], ASM-nnn ids — provenance link (one of three required for create)",
        "depends_on_decisions": "list[str], DEC-nnn ids — provenance link (one of three required for create)",
        "change_reason": "str, why this write happened — recorded on the event and, for revise, on history",
    },
    required=["operation", "project_slug"],
    optional=[
        "entity_id", "statement", "type", "priority", "confidence", "confidence_basis", "covers_areas",
        "derived_from_answers", "depends_on_assumptions", "depends_on_decisions", "change_reason",
    ],
    formats={
        "operation": "one of: create, revise, confirm, reject, supersede",
        "type": "one of: functional, non_functional, constraint",
        "priority": "one of: must, should, could, wont_v1",
        "confidence": "one of: HIGH, MEDIUM, LOW",
    },
    returns="ToolResult with data={entity_id, event_id, replayed} on success.",
    examples=[
        'manage_requirement(operation="create", project_slug="invoice-tracker", statement="Users can export invoices as PDF", type="functional", priority="must", confidence="HIGH", confidence_basis="user said it directly", covers_areas=["jobs"], derived_from_answers=["ANS-001"])',
        'manage_requirement(operation="confirm", project_slug="invoice-tracker", entity_id="REQ-001")',
    ],
    edge_cases=[
        "create with covers_areas=[] is rejected as VALIDATION, naming the valid area keys",
        "create with no provenance link at all is rejected as VALIDATION",
        "confirm on a requirement whose area has an open blocking Unknown is rejected as BUSINESS",
    ],
    limitations=[
        "cannot change a requirement's covers_areas or statement once CONFIRMED — supersede and create a new one instead",
    ],
    use_when=[
        "the agent has enough provenance (an answer, assumption or decision) to record a real requirement",
        "the user has explicitly confirmed or rejected a proposed requirement",
    ],
    do_not_use_when=[
        "the agent wants to record research — use manage_research (Guidance/Research subagent grant, not Discovery)",
        "the agent only wants to read current requirements — use read_planning_state instead",
    ],
    related_tools={
        "read_planning_state": "reads Requirement entities; never writes them",
        "manage_assumption": "writes Assumption entities, a different schema and transition set",
    },
)

MANAGE_ASSUMPTION_SPEC = ToolSpec(
    name="manage_assumption",
    purpose="Create or change the status of an Assumption — the only tool that ever writes ASM-nnn entities.",
    inputs={
        "operation": "str, one of create|confirm|reject|modify|supersede",
        "project_slug": "str, the project's slug",
        "entity_id": "str, ASM-nnn — required for confirm/reject/modify/supersede",
        "statement": "str, the assumption text — required for create",
        "reason": "str, why the agent inferred this — required for create",
        "impact": "str, one of HIGH|MEDIUM|LOW — required for create",
        "confidence": "str, one of HIGH|MEDIUM|LOW — required for create",
        "confidence_basis": "str, non-empty justification for confidence — required for create",
        "change_reason": "str, why this write happened",
    },
    required=["operation", "project_slug"],
    optional=["entity_id", "statement", "reason", "impact", "confidence", "confidence_basis", "change_reason"],
    formats={
        "operation": "one of: create, confirm, reject, modify, supersede",
        "impact": "one of: HIGH, MEDIUM, LOW",
        "confidence": "one of: HIGH, MEDIUM, LOW",
    },
    returns="ToolResult with data={entity_id, event_id, replayed} on success.",
    examples=[
        'manage_assumption(operation="create", project_slug="invoice-tracker", statement="Single currency (USD) for v1", reason="no mention of multi-currency in the seed requirement", impact="MEDIUM", confidence="MEDIUM", confidence_basis="strongly implied by scope")',
        'manage_assumption(operation="confirm", project_slug="invoice-tracker", entity_id="ASM-001")',
    ],
    edge_cases=[
        "modify on a CONFIRMED assumption is rejected — modify only PROPOSED, supersede a CONFIRMED one instead",
    ],
    limitations=[
        "cannot flip status backwards — REJECTED/SUPERSEDED are terminal",
    ],
    use_when=[
        "the agent needs to record something it inferred rather than was told, to keep moving without asking",
        "the user has confirmed or rejected a previously recorded assumption",
    ],
    do_not_use_when=[
        "the user stated this directly — use manage_requirement instead, this is for inferred content only",
        "the agent only wants to read current assumptions — use read_planning_state instead",
    ],
    related_tools={
        "manage_requirement": "writes Requirement entities, a different schema and transition set",
        "read_planning_state": "reads Assumption entities; never writes them",
    },
)

MANAGE_DECISION_SPEC = ToolSpec(
    name="manage_decision",
    purpose="Open, defer, decide or supersede a Decision — the only tool that ever writes DEC-nnn entities.",
    inputs={
        "operation": "str, one of open|defer|decide|supersede",
        "project_slug": "str, the project's slug",
        "entity_id": "str, DEC-nnn — required for defer/decide/supersede",
        "question": "str, the decision framed as a choice — required for open",
        "owner": "str, who owns this decision — required for open and defer",
        "owner_type": "str, one of user|external|agent — required for open and defer",
        "defer_reason": "str, why this is being deferred — required for defer",
        "chosen_option": "str, the option chosen — required for decide",
        "rationale": "str, why that option was chosen — required for decide",
        "affects": "str, one of architecture|scope|other — feeds the expected_decision_date rule",
        "blocking": "bool, does this stop planning from reaching READY — default False",
    },
    required=["operation", "project_slug"],
    optional=["entity_id", "question", "owner", "owner_type", "defer_reason", "chosen_option", "rationale", "affects", "blocking"],
    formats={
        "operation": "one of: open, defer, decide, supersede",
        "owner_type": "one of: user, external, agent",
        "affects": "one of: architecture, scope, other",
    },
    returns="ToolResult with data={entity_id, event_id, replayed} on success. defer's resulting entity always carries a computed expected_decision_date (T12's rule) — never caller-supplied.",
    examples=[
        'manage_decision(operation="open", project_slug="invoice-tracker", question="Which payment processor?", owner="user:jane", owner_type="user", blocking=True, affects="architecture")',
        'manage_decision(operation="defer", project_slug="invoice-tracker", entity_id="DEC-001", defer_reason="waiting on finance team", owner="user:jane", owner_type="user")',
    ],
    edge_cases=[
        "defer without defer_reason, owner or owner_type is rejected as VALIDATION",
        "decide from OPEN or DECIDE_LATER both succeed; decide on a SUPERSEDED decision is rejected as BUSINESS",
    ],
    limitations=[
        "expected_decision_date is never caller-supplied — always recomputed from blocking/affects at defer time",
    ],
    use_when=[
        "the agent needs to frame an open question as a choice among options, with an owner",
        "the owner cannot decide right now and needs a deferral with a real follow-up date",
    ],
    do_not_use_when=[
        "the open item isn't yet framed as a choice — use manage_unknown instead",
        "the agent only wants to read current decisions — use read_planning_state instead",
    ],
    related_tools={
        "manage_unknown": "writes Unknown entities — use before a question is framed as a Decision",
        "read_planning_state": "reads Decision entities; never writes them",
    },
)

MANAGE_UNKNOWN_SPEC = ToolSpec(
    name="manage_unknown",
    purpose="Record, classify, resolve or convert an Unknown — the only tool that ever writes UNK-nnn entities.",
    inputs={
        "operation": "str, one of record|classify|resolve|convert",
        "project_slug": "str, the project's slug",
        "entity_id": "str, UNK-nnn — required for classify/resolve/convert",
        "question": "str, what is not yet known — required for record",
        "area": "str, an area key from config/areas.py — required for record",
        "why_it_matters": "str, why this matters — required for record",
        "blocking": "bool, does this stop planning from reaching READY — required for record",
        "route": "str, one of GUIDANCE|RESEARCH|USER_DECISION|ASSUMPTION|OPTIONAL|FUTURE — required for record",
        "owner_type": "str, one of user|external|agent — required for record",
        "converted_to": "str, the entity id this Unknown became — required for convert",
    },
    required=["operation", "project_slug"],
    optional=["entity_id", "question", "area", "why_it_matters", "blocking", "route", "owner_type", "converted_to"],
    formats={
        "operation": "one of: record, classify, resolve, convert",
        "route": "one of: GUIDANCE, RESEARCH, USER_DECISION, ASSUMPTION, OPTIONAL, FUTURE",
        "owner_type": "one of: user, external, agent",
    },
    returns="ToolResult with data={entity_id, event_id, replayed} on success.",
    examples=[
        'manage_unknown(operation="record", project_slug="invoice-tracker", question="What accounting system does the client use?", area="existing_system", why_it_matters="determines the integration approach", blocking=True, route="USER_DECISION", owner_type="user")',
        'manage_unknown(operation="convert", project_slug="invoice-tracker", entity_id="UNK-001", converted_to="DEC-002")',
    ],
    edge_cases=[
        "record without both blocking and route is rejected as VALIDATION — both are mandatory, never defaulted",
        "convert with a converted_to id that does not exist is rejected as BUSINESS",
    ],
    limitations=[
        "classify only runs while the Unknown is still OPEN — RESOLVED/CONVERTED are terminal",
    ],
    use_when=[
        "the agent has identified something not yet known and needs to record it with a resolution route",
        "an Unknown has actually been resolved or converted into a real entity",
    ],
    do_not_use_when=[
        "the question is already framed as a choice among options — use manage_decision instead",
        "the agent only wants to read current unknowns — use read_planning_state instead",
    ],
    related_tools={
        "manage_decision": "writes Decision entities — for questions already framed as a choice",
        "read_planning_state": "reads Unknown entities; never writes them",
    },
)

register(MANAGE_REQUIREMENT_SPEC, _manage_requirement_handler, owner_agents=["discovery"])
register(MANAGE_ASSUMPTION_SPEC, _manage_assumption_handler, owner_agents=["discovery"])
register(MANAGE_DECISION_SPEC, _manage_decision_handler, owner_agents=["discovery"])
register(MANAGE_UNKNOWN_SPEC, _manage_unknown_handler, owner_agents=["discovery"])
