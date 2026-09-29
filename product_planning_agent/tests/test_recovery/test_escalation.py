"""T32 tests — escalation (`ppa/orchestrator/escalation.py`). Every
Done-when box in `tasks/t32_transactions_retry_recovery.md` that concerns
escalation maps to at least one test here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ppa.orchestrator.escalation import Escalation, EscalationTrigger, render_escalation

_ALL_TRIGGERS = list(EscalationTrigger)


def _escalation(trigger: EscalationTrigger, **overrides) -> Escalation:
    base = dict(
        trigger=trigger,
        what_happened="a critical requirement could not be determined from the conversation so far",
        what_is_missing="which payment processor the client will actually use",
        what_was_attempted="asked twice, offered Guidance Mode's own proposal, still unanswered",
        options=["assume Stripe and flag it HIGH-impact", "route to the client questionnaire", "wait for the user"],
        question="Which of these three should I do — assume Stripe, ask the client, or wait for you?",
    )
    base.update(overrides)
    return Escalation(**base)


# ---------------------------------------------------------------------------
# Done when: every escalation path ends in a concrete question — a test
# asserts no escalation renders without one.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trigger", _ALL_TRIGGERS)
def test_every_trigger_can_build_a_real_escalation_that_ends_in_a_question(trigger):
    escalation = _escalation(trigger)
    rendered = render_escalation(escalation)

    assert rendered.strip().endswith(escalation.question)
    assert "**What I need from you:**" in rendered
    assert escalation.question in rendered


def test_an_escalation_cannot_be_constructed_with_an_empty_question():
    with pytest.raises(ValidationError):
        _escalation(EscalationTrigger.PLAN_APPROVAL, question="")


def test_an_escalation_cannot_be_constructed_with_no_options():
    with pytest.raises(ValidationError):
        _escalation(EscalationTrigger.PLAN_APPROVAL, options=[])


def test_an_escalation_cannot_be_constructed_with_any_blank_required_field():
    for field in ("what_happened", "what_is_missing", "what_was_attempted"):
        with pytest.raises(ValidationError):
            _escalation(EscalationTrigger.PLAN_APPROVAL, **{field: "   "})


def test_render_escalation_states_the_five_parts_in_order():
    escalation = _escalation(EscalationTrigger.HIGH_IMPACT_ASSUMPTION_AWAITING_CONFIRMATION)
    rendered = render_escalation(escalation)

    order = ["What happened", "What is missing", "What was attempted", "Options", "What I need from you"]
    positions = [rendered.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_all_seven_named_triggers_exist():
    expected = {
        "critical_requirement_undetermined",
        "conflicting_user_decisions",
        "business_rule_conflict",
        "permission_conflict",
        "repeated_tool_failure",
        "plan_approval",
        "high_impact_assumption_awaiting_confirmation",
    }
    assert {t.value for t in EscalationTrigger} == expected
