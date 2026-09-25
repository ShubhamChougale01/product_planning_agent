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

from typing import Any, Callable, Mapping

from ppa.engines.coverage import compute_coverage, progress
from ppa.engines.impact import analyze_impact
from ppa.engines.open_items import collect_open_items
from ppa.engines.readiness import check_readiness
from ppa.ledger.digest import generate_digest
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import BaseEntity
from ppa.ledger.project import DEFAULT_PROJECTS_ROOT, Project, open_project
from ppa.results.categories import ErrorCategory, RecoveryAction
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
