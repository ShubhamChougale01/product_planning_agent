"""Delivery tools — declared, stubbed (T18, DESIGN.md §2.1, §2.8, §2.19.2,
S5.7, S5.9).

Delivery is v3. Its five tools per §2.8 are `read_planning_state` (already
registered and granted to Delivery by `ppa/tools/discovery_tools.py`, T15)
plus the four below. Three are pure stubs, same shape as `ppa/tools/
planning_tools.py`. `manage_linear_issue` is different: Linear itself is
not real yet, but its **guardrails** are — the plan-approval business rule
and the approval gate (`ppa/tools/approval.py`) are both live and tested
now, against this stub, exactly as DESIGN.md's own "built in v1 against the
stubs" framing requires. Creating an issue never actually calls an external
API; what's real is that it refuses to create anything without a plan in
`APPROVED` status and a matching, unexpired approval.
"""

from __future__ import annotations

from typing import Any

from ppa.ledger.audit import AuditResult, record_audit
from ppa.ledger.project import Project
from ppa.ledger.store import ledger_version
from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult
from ppa.tools.approval import compute_scope_hash, requires_approval
from ppa.tools.registry import register
from ppa.tools.spec import ToolSpec
from ppa.validation import infer_validation_layer

_STUB_MESSAGE = "Delivery is v3. Planning must be approved before delivery tools do anything."


def _not_implemented(tool_name: str) -> ToolResult:
    rule = CATEGORY_RULES[ErrorCategory.NOT_IMPLEMENTED]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.NOT_IMPLEMENTED,
            code="DELIVERY_NOT_BUILT",
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=f"{tool_name}: {_STUB_MESSAGE}",
        ),
    )


def _error(category: ErrorCategory, code: str, description: str) -> ToolResult:
    rule = CATEGORY_RULES[category]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=category,
            code=code,
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=description,
        ),
    )


def read_approved_plan(project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("read_approved_plan")


def generate_story(project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("generate_story")


def validate_story(project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("validate_story")


# --- manage_linear_issue: the one Delivery tool with real guardrails ------


def _linear_issue_scope(operation: str, kwargs: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Only `create` needs an approval; any other operation is not gated —
    there isn't one yet (v1 only defines `create`), so this always fires
    for the one operation this stub actually accepts."""

    if operation != "create":
        return None
    story_ids = list(kwargs.get("story_ids") or [])
    return compute_scope_hash(story_ids), story_ids


def _audit_linear(project: Project, *, agent_id: str, workflow_state: str, args: dict[str, Any], reason: str, result: ToolResult) -> ToolResult:
    version = ledger_version(project.events_path)
    error = result.error
    record_audit(
        agent=agent_id, tool="manage_linear_issue", operation="write" if result.success else "reject",
        workflow_state=workflow_state, inputs=args, reason=reason,
        result=AuditResult(success=result.success, category=error.category if error else None, code=error.code if error else None),
        path=project.audit_path, validation_layer_failed=infer_validation_layer(error),
        ledger_version_before=version, ledger_version_after=version,
    )
    return result


@requires_approval(_linear_issue_scope)
def manage_linear_issue(
    operation: str,
    project: Project,
    *,
    actor_id: str = "agent:delivery",
    session_id: str = "session-unknown",
    workflow_state: str = "DISCOVERY",
    agent_id: str = "delivery",
    now: Any = None,
    **kwargs: Any,
) -> ToolResult:
    """`create` only in v1. Gated by `@requires_approval` (checked before
    this body ever runs) and, inside the body, by `plan_status ==
    "APPROVED"` — DESIGN.md's own eval case 12: "creating an issue with no
    approval, with an expired approval, or with an approval whose
    scope_hash no longer matches must each return BUSINESS and create
    nothing," plus "`manage_linear_issue` returns BUSINESS when
    `plan.status != APPROVED`" (S5.7), both true today against this stub."""

    tool = "manage_linear_issue"
    args = {"operation": operation, **kwargs}

    if operation != "create":
        result = _error(ErrorCategory.VALIDATION, "UNKNOWN_OPERATION", f"{tool}: unknown operation {operation!r} — only 'create' exists in v1")
        return _audit_linear(project, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="unknown operation", result=result)

    plan_status = kwargs.get("plan_status")
    if plan_status != "APPROVED":
        result = _error(ErrorCategory.BUSINESS, "PLAN_NOT_APPROVED", f"{tool}(create): plan.status must be APPROVED, got {plan_status!r}")
        return _audit_linear(project, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="plan not approved", result=result)

    story_ids = list(kwargs.get("story_ids") or [])
    if not story_ids:
        result = _error(ErrorCategory.VALIDATION, "MISSING_STORY_IDS", f"{tool}(create) requires a non-empty story_ids list")
        return _audit_linear(project, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="missing story_ids", result=result)

    created = [f"LINEAR-STUB-{sid}" for sid in story_ids]
    result = ToolResult(
        success=True, result_count=len(created),
        data={"created_issue_ids": created, "note": "v1 stub — the gate is real, the Linear API call is not (v3)"},
    )
    return _audit_linear(project, agent_id=agent_id, workflow_state=workflow_state, args=args, reason="linear issues created (stub)", result=result)


async def _stub_handler(writer: Any, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = writer(None, **args)
    return {"content": [{"type": "text", "text": result.model_dump_json()}], "is_error": not result.success}


async def _read_approved_plan_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _stub_handler(read_approved_plan, "read_approved_plan", args)


async def _generate_story_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _stub_handler(generate_story, "generate_story", args)


async def _validate_story_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _stub_handler(validate_story, "validate_story", args)


async def _manage_linear_issue_handler(args: dict[str, Any]) -> dict[str, Any]:
    from ppa.ledger.project import DEFAULT_PROJECTS_ROOT, open_project

    project_slug = args.get("project_slug")
    operation = args.get("operation", "")
    if not project_slug:
        result = _error(ErrorCategory.VALIDATION, "MISSING_PROJECT_SLUG", "manage_linear_issue: requires project_slug")
    else:
        projects_root = args.get("projects_root", DEFAULT_PROJECTS_ROOT)
        project = open_project(project_slug, projects_root=projects_root)
        kwargs = {k: v for k, v in args.items() if k not in ("operation", "project_slug", "projects_root")}
        result = manage_linear_issue(operation, project, **kwargs)
    return {"content": [{"type": "text", "text": result.model_dump_json()}], "is_error": not result.success}


def _stub_spec(name: str, purpose: str, inputs: dict[str, str], example_a: str, example_b: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        purpose=purpose,
        inputs=inputs,
        required=list(inputs),
        optional=[],
        returns="NOT_IMPLEMENTED with recommended_action=INFORM_USER — Delivery is v3.",
        examples=[example_a, example_b],
        edge_cases=["every call in v1 returns NOT_IMPLEMENTED, regardless of input"],
        limitations=["not implemented until Delivery (v3) lands"],
        use_when=[
            "never in v1 — this tool has no working implementation yet",
            "kept declared so the Delivery boundary is testable before the feature exists",
        ],
        do_not_use_when=[
            "the plan is not yet approved — nothing in Delivery can run before PLAN_APPROVED",
            "the agent wants to read state — use read_planning_state instead, that one is real",
        ],
        related_tools={"read_planning_state": "the one Delivery tool that actually works in v1"},
    )


READ_APPROVED_PLAN_SPEC = _stub_spec(
    "read_approved_plan", "Read the approved plan (v3 — not implemented in v1).",
    {"project_slug": "str, the project's slug"},
    'read_approved_plan(project_slug="invoice-tracker")',
    'read_approved_plan(project_slug="invoice-tracker", milestone_id="MS-001")',
)
GENERATE_STORY_SPEC = _stub_spec(
    "generate_story", "Generate an implementation story from an approved plan item (v3 — not implemented in v1).",
    {"project_slug": "str, the project's slug"},
    'generate_story(project_slug="invoice-tracker")',
    'generate_story(project_slug="invoice-tracker", plan_item_id="PLN-001")',
)
VALIDATE_STORY_SPEC = _stub_spec(
    "validate_story", "Validate a generated story against its source requirement (v3 — not implemented in v1).",
    {"project_slug": "str, the project's slug"},
    'validate_story(project_slug="invoice-tracker")',
    'validate_story(project_slug="invoice-tracker", story_id="STORY-001")',
)

MANAGE_LINEAR_ISSUE_SPEC = ToolSpec(
    name="manage_linear_issue",
    purpose="Create an implementation issue in Linear from an approved Delivery story — real guardrails, stubbed external call.",
    inputs={
        "operation": "str, only 'create' exists in v1",
        "project_slug": "str, the project's slug",
        "plan_status": "str, the plan's current status — must equal APPROVED",
        "story_ids": "list[str], the exact story ids this call would create issues for",
    },
    required=["operation", "project_slug", "plan_status", "story_ids"],
    optional=[],
    formats={"operation": "one of: create"},
    returns="ToolResult with data={created_issue_ids, note} on success — a stub id, not a real Linear issue.",
    examples=[
        'manage_linear_issue(operation="create", project_slug="invoice-tracker", plan_status="APPROVED", story_ids=["STORY-001", "STORY-002"])',
        'manage_linear_issue(operation="create", project_slug="invoice-tracker", plan_status="DRAFT", story_ids=["STORY-001"])  # -> BUSINESS, plan not approved',
    ],
    edge_cases=[
        "no approval on record for this exact story set -> BUSINESS, creates nothing",
        "an expired approval -> BUSINESS, creates nothing",
        "an approval whose scope_hash no longer matches this story set -> BUSINESS, creates nothing",
        "plan_status != APPROVED -> BUSINESS, creates nothing, checked even with a valid approval",
    ],
    limitations=[
        "no external Linear API call is actually made in v1 — created_issue_ids are stub ids",
    ],
    use_when=[
        "workflow_state == PLAN_APPROVED and the story set has an active, matching approval",
        "never called directly by Discovery — Discovery is not granted this tool at all",
    ],
    do_not_use_when=[
        "the plan is draft or in review -> BUSINESS",
        "the user has not yet approved this exact batch -> BUSINESS, use the approval gate first",
    ],
    related_tools={
        "read_planning_state": "reads ledger state; never creates anything external",
        "generate_story": "produces the story; does not push it anywhere",
    },
)

register(READ_APPROVED_PLAN_SPEC, _read_approved_plan_handler, owner_agents=["delivery"])
register(GENERATE_STORY_SPEC, _generate_story_handler, owner_agents=["delivery"])
register(VALIDATE_STORY_SPEC, _validate_story_handler, owner_agents=["delivery"])
register(MANAGE_LINEAR_ISSUE_SPEC, _manage_linear_issue_handler, owner_agents=["delivery"])
