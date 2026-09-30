"""T22 — agent prohibitions from DESIGN.md §2.4. One test per prohibition,
checked directly against `ppa.agents.registry.GRANTS` — the single source
of truth the permission layer (T14) already enforces at every call, so a
prohibition holding here is a prohibition that holds everywhere.

Every "must not" below is a passing test before any agent prompt exists —
prompt text is not a boundary; an empty grant set is (DESIGN.md §2.10:
"Prohibitions are enforced by the permission layer, not by prompt text.").
"""

from __future__ import annotations

from ppa.agents.registry import GRANTS

DOMAIN_TOOLS = frozenset(
    {
        "read_planning_state",
        "manage_requirement",
        "manage_assumption",
        "manage_decision",
        "manage_unknown",
        "ask_user",
        "request_guidance",
        "manage_research",
        "manage_plan",
        "manage_milestone",
        "manage_timeline",
        "analyze_plan_impact",
        "read_approved_plan",
        "generate_story",
        "validate_story",
        "manage_linear_issue",
    }
)
"""Every real tool any agent (other than the Orchestrator) is granted
today — used to prove the Orchestrator's own grant set is disjoint from
all of it, not just missing a couple of names by coincidence."""


# ---------------------------------------------------------------------------
# Discovery must not create a plan, generate stories, or touch Linear.
# ---------------------------------------------------------------------------


def test_discovery_is_not_granted_plan_tools():
    assert "manage_plan" not in GRANTS["discovery"]
    assert "manage_milestone" not in GRANTS["discovery"]
    assert "manage_timeline" not in GRANTS["discovery"]


def test_discovery_is_not_granted_story_generation():
    assert "generate_story" not in GRANTS["discovery"]
    assert "validate_story" not in GRANTS["discovery"]


def test_discovery_is_not_granted_linear():
    assert "manage_linear_issue" not in GRANTS["discovery"]


# ---------------------------------------------------------------------------
# Planning must not create Linear issues, invent requirements, or promote
# an assumption to CONFIRMED without an explicit user confirmation event.
# ---------------------------------------------------------------------------


def test_planning_is_not_granted_linear():
    assert "manage_linear_issue" not in GRANTS["planning"]


def test_planning_is_not_granted_requirement_authoring():
    assert "manage_requirement" not in GRANTS["planning"]


def test_planning_is_not_granted_assumption_writes_at_all():
    """Planning has no path to promote an assumption to CONFIRMED (or any
    other status) itself — it is not granted `manage_assumption` at all, so
    "without an explicit user confirmation event" holds trivially: there is
    no event Planning could ever produce for this."""

    assert "manage_assumption" not in GRANTS["planning"]


# ---------------------------------------------------------------------------
# Delivery must not modify approved requirements, or generate work from a
# non-APPROVED plan.
# ---------------------------------------------------------------------------


def test_delivery_is_not_granted_requirement_writes():
    assert "manage_requirement" not in GRANTS["delivery"]


def test_delivery_generating_work_from_a_non_approved_plan_is_rejected_at_workflow_layer():
    """"Generate work from a non-APPROVED plan" is DESIGN.md's own
    `generate_story` guardrail (workflow layer, DISCOVERY state ->
    REJECT — see `tests/test_permissions/test_guardrails.py`), not a grant
    gap: Delivery *is* granted `generate_story`, exactly as it must be to
    ever do its job once a plan really is approved. The check that matters
    is legality-by-state, not permission."""

    from ppa.validation import workflow

    result = workflow.check("generate_story", "DISCOVERY")
    assert result is not None
    assert result.error.category.value == "BUSINESS"


# ---------------------------------------------------------------------------
# Orchestrator must not hold domain tools or write requirements.
# ---------------------------------------------------------------------------


def test_orchestrator_holds_zero_domain_tools():
    assert GRANTS["orchestrator"] & DOMAIN_TOOLS == frozenset()


def test_orchestrator_cannot_write_requirements():
    assert "manage_requirement" not in GRANTS["orchestrator"]


def test_orchestrator_grant_set_is_exactly_its_own_coordination_tools():
    assert GRANTS["orchestrator"] == frozenset(
        {
            "read_workflow_state",
            "invoke_discovery",
            "invoke_planning",
            "invoke_delivery",
            "review_subagent_result",
        }
    )
