"""Escalation to the user when recovery is exhausted (T32, DESIGN.md §2.14,
§2.15, S11.1-S11.4).

**"An escalation that does not end in a concrete question is a bug."** This
task's own instruction, enforced structurally rather than by convention:
`Escalation.question` is a required, non-empty field — the model cannot
construct one that omits it, the same discipline `ppa.ledger.audit.
AuditRecord.reason` and `ppa.ledger.models.ConfidenceMixin.confidence_basis`
already apply to their own required-explanation fields.

Every escalation states, **in this order**: what happened, what is missing,
what was attempted, what the options are, what decision is needed —
`render_escalation` renders exactly that order, always.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EscalationTrigger(str, Enum):
    """The seven triggers this task's own "Escalation" section names,
    verbatim."""

    CRITICAL_REQUIREMENT_UNDETERMINED = "critical_requirement_undetermined"
    CONFLICTING_USER_DECISIONS = "conflicting_user_decisions"
    BUSINESS_RULE_CONFLICT = "business_rule_conflict"
    PERMISSION_CONFLICT = "permission_conflict"
    REPEATED_TOOL_FAILURE = "repeated_tool_failure"
    PLAN_APPROVAL = "plan_approval"
    HIGH_IMPACT_ASSUMPTION_AWAITING_CONFIRMATION = "high_impact_assumption_awaiting_confirmation"


class Escalation(BaseModel):
    """One escalation, in the five parts this task's own instruction
    requires, in order. `question` and `options` are both required and
    non-empty — an escalation that could otherwise construct with
    "nothing to ask" or "nothing to choose from" would be exactly the bug
    this task's own instruction warns against."""

    model_config = ConfigDict(extra="forbid")

    trigger: EscalationTrigger
    what_happened: str
    what_is_missing: str
    what_was_attempted: str
    options: list[str]
    question: str

    @field_validator("what_happened", "what_is_missing", "what_was_attempted", "question")
    @classmethod
    def _required_and_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("every escalation field must be a real, non-empty explanation")
        return v

    @field_validator("options")
    @classmethod
    def _at_least_one_option(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("an escalation must state at least one option — never a dead end")
        return v


def render_escalation(escalation: Escalation) -> str:
    """What happened · what is missing · what was attempted · the options ·
    the question — in that order, always. The last line is always the
    concrete question a person can actually answer, never buried mid-way
    through."""

    lines = [
        f"**What happened:** {escalation.what_happened}",
        f"**What is missing:** {escalation.what_is_missing}",
        f"**What was attempted:** {escalation.what_was_attempted}",
        "**Options:**",
    ]
    lines.extend(f"- {option}" for option in escalation.options)
    lines.append(f"**What I need from you:** {escalation.question}")
    return "\n".join(lines)
