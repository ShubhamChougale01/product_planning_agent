"""Planning tools — declared, stubbed (T18, DESIGN.md §2.1, §2.8).

Planning is v2. Its five tools per §2.8 are `read_planning_state` (already
registered and granted to Planning by `ppa/tools/discovery_tools.py`, T15 —
nothing to add here) plus the four below, declared with full `ToolSpec`s
and real grants now so the *boundary* exists before the feature does. A
stub is a real registration with real grants and a real guardrail — not a
`pass`. Every body here returns `NOT_IMPLEMENTED`/`INFORM_USER`
unconditionally; there is no input shape that makes any of them succeed
yet.
"""

from __future__ import annotations

from typing import Any

from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult
from ppa.tools.registry import register
from ppa.tools.spec import ToolSpec

_STUB_MESSAGE = "Planning is v2. Discovery is validated and the ledger is ready for it."


def _not_implemented(tool_name: str) -> ToolResult:
    rule = CATEGORY_RULES[ErrorCategory.NOT_IMPLEMENTED]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.NOT_IMPLEMENTED,
            code="PLANNING_NOT_BUILT",
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=f"{tool_name}: {_STUB_MESSAGE}",
        ),
    )


def manage_plan(operation: str, project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("manage_plan")


def manage_milestone(operation: str, project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("manage_milestone")


def manage_timeline(operation: str, project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("manage_timeline")


def analyze_plan_impact(project: Any, **kwargs: Any) -> ToolResult:
    return _not_implemented("analyze_plan_impact")


async def _stub_handler(writer: Any, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = writer(args.get("operation", ""), None, **{k: v for k, v in args.items() if k != "operation"})
    return {"content": [{"type": "text", "text": result.model_dump_json()}], "is_error": not result.success}


async def _manage_plan_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _stub_handler(manage_plan, "manage_plan", args)


async def _manage_milestone_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _stub_handler(manage_milestone, "manage_milestone", args)


async def _manage_timeline_handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _stub_handler(manage_timeline, "manage_timeline", args)


async def _analyze_plan_impact_handler(args: dict[str, Any]) -> dict[str, Any]:
    result = analyze_plan_impact(None, **args)
    return {"content": [{"type": "text", "text": result.model_dump_json()}], "is_error": not result.success}


def _stub_spec(name: str, purpose: str, inputs: dict[str, str], example_a: str, example_b: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        purpose=purpose,
        inputs=inputs,
        required=list(inputs),
        optional=[],
        returns="NOT_IMPLEMENTED with recommended_action=INFORM_USER — Planning is v2.",
        examples=[example_a, example_b],
        edge_cases=["every call in v1 returns NOT_IMPLEMENTED, regardless of input"],
        limitations=["not implemented until Planning (v2) lands"],
        use_when=[
            "never in v1 — this tool has no working implementation yet",
            "kept declared so the Planning boundary is testable before the feature exists",
        ],
        do_not_use_when=[
            "the ledger is still in Discovery — advance through DISCOVERY_VALIDATED first",
            "the agent wants to read state — use read_planning_state instead, that one is real",
        ],
        related_tools={"read_planning_state": "the one Planning tool that actually works in v1"},
    )


MANAGE_PLAN_SPEC = _stub_spec(
    "manage_plan", "Create or change a Plan (v2 — not implemented in v1).",
    {"operation": "str, plan operation", "project_slug": "str, the project's slug"},
    'manage_plan(operation="create", project_slug="invoice-tracker")',
    'manage_plan(operation="revise", project_slug="invoice-tracker")',
)
MANAGE_MILESTONE_SPEC = _stub_spec(
    "manage_milestone", "Create or change a Milestone (v2 — not implemented in v1).",
    {"operation": "str, milestone operation", "project_slug": "str, the project's slug"},
    'manage_milestone(operation="create", project_slug="invoice-tracker")',
    'manage_milestone(operation="revise", project_slug="invoice-tracker")',
)
MANAGE_TIMELINE_SPEC = _stub_spec(
    "manage_timeline", "Create or change a Timeline (v2 — not implemented in v1).",
    {"operation": "str, timeline operation", "project_slug": "str, the project's slug"},
    'manage_timeline(operation="create", project_slug="invoice-tracker")',
    'manage_timeline(operation="revise", project_slug="invoice-tracker")',
)
ANALYZE_PLAN_IMPACT_SPEC = _stub_spec(
    "analyze_plan_impact", "Traverse plan-level impact (v2 — not implemented in v1).",
    {"project_slug": "str, the project's slug"},
    'analyze_plan_impact(project_slug="invoice-tracker")',
    'analyze_plan_impact(project_slug="invoice-tracker", entity_id="REQ-001")',
)

register(MANAGE_PLAN_SPEC, _manage_plan_handler, owner_agents=["planning"])
register(MANAGE_MILESTONE_SPEC, _manage_milestone_handler, owner_agents=["planning"])
register(MANAGE_TIMELINE_SPEC, _manage_timeline_handler, owner_agents=["planning"])
register(ANALYZE_PLAN_IMPACT_SPEC, _analyze_plan_impact_handler, owner_agents=["planning"])
