"""T30 eval — REVIEW mode: walking assumptions and the missing approval fact.

Walking assumptions individually, the approval event, and the readiness
gate wiring are all mechanical — proven directly against the real
`manage_assumption` writer and `grant_review_approval`, no model needed.
Actually presenting the review conversationally, and walking a real batch
of HIGH-impact assumptions one at a time, is the model's own job, proven
live once in `test_a_real_review_turn_walks_assumptions_individually`
(marked `live_model`).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.agents.discovery import DiscoveryMode, allowed_tools_for_mode
from ppa.agents.modes.review import (
    current_review_approval,
    evaluate_review_round,
    grant_review_approval,
    readiness_gate_inputs,
    run_review_session,
)
from ppa.config.profiles import UserProfile
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.tools.discovery_tools import manage_assumption

NOW = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="product", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Review Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-review", now=NOW)
    base.update(overrides)
    return base


def _seed_high_assumption(project, statement: str) -> str:
    result = manage_assumption(
        "create", project, **_writer_kwargs(),
        statement=statement, reason="inferred from the seed requirement", impact="HIGH",
        confidence="MEDIUM", confidence_basis="a reasonable default, not yet confirmed",
    )
    assert result.success is True, result.error
    return result.data["entity_id"]


# ---------------------------------------------------------------------------
# Done when: every HIGH-impact assumption is walked individually.
# ---------------------------------------------------------------------------


def test_review_grant_includes_manage_assumption_but_not_ask_user():
    subset = allowed_tools_for_mode(DiscoveryMode.REVIEW)
    assert "manage_assumption" in subset
    assert "ask_user" not in subset
    assert "manage_requirement" not in subset  # nothing left to propose, per mode_review.md


def test_walking_every_high_assumption_individually_satisfies_the_round(tmp_path):
    project = _make_project(tmp_path)
    asm_a = _seed_high_assumption(project, "Payments settle in USD only for v1")
    asm_b = _seed_high_assumption(project, "Only one approver is needed per invoice")

    before = current_entities(project.events_path)
    high_proposed_before = {eid: e for eid, e in before.items() if getattr(e, "impact", None) == "HIGH" and e.status == "PROPOSED"}
    assert set(high_proposed_before) == {asm_a, asm_b}

    confirmed = manage_assumption("confirm", project, **_writer_kwargs(), entity_id=asm_a)
    assert confirmed.success is True, confirmed.error
    rejected = manage_assumption("reject", project, **_writer_kwargs(), entity_id=asm_b)
    assert rejected.success is True, rejected.error

    after = current_entities(project.events_path)
    report = evaluate_review_round(high_proposed_before, after)
    assert report.ok, report.violations
    assert report.assumptions_walked_individually == 2


def test_a_still_proposed_high_assumption_fails_the_round(tmp_path):
    project = _make_project(tmp_path)
    asm_a = _seed_high_assumption(project, "Payments settle in USD only for v1")

    before = current_entities(project.events_path)
    high_proposed_before = {eid: e for eid, e in before.items() if getattr(e, "impact", None) == "HIGH" and e.status == "PROPOSED"}

    after = current_entities(project.events_path)  # nothing happened — still PROPOSED
    report = evaluate_review_round(high_proposed_before, after)
    assert not report.ok
    assert any("never walked" in v for v in report.violations)


# ---------------------------------------------------------------------------
# Done when: READY is unreachable without an explicit user approval event.
# ---------------------------------------------------------------------------


def test_readiness_gate_condition_seven_requires_a_real_approval_event(tmp_path):
    project = _make_project(tmp_path)
    entities = current_entities(project.events_path)

    approved, confirmed_areas = readiness_gate_inputs(project.events_path)
    assert approved is False
    assert confirmed_areas == set()

    _ready, blockers = check_readiness(entities, _profile(), review_approved=approved, confirmed_areas=confirmed_areas)
    assert any(b.condition == "review_not_approved" for b in blockers)

    grant_review_approval(
        project.events_path, approved_areas=["problem", "users"], approved_by="user:shubham",
        actor_id="user:shubham", session_id="sess-review", now=NOW,
    )

    approved, confirmed_areas = readiness_gate_inputs(project.events_path)
    assert approved is True
    assert confirmed_areas == {"problem", "users"}

    _ready, blockers = check_readiness(entities, _profile(), review_approved=approved, confirmed_areas=confirmed_areas)
    assert not any(b.condition == "review_not_approved" for b in blockers)


def test_current_review_approval_reflects_the_latest_grant(tmp_path):
    project = _make_project(tmp_path)
    assert current_review_approval(project.events_path) is None

    grant_review_approval(
        project.events_path, approved_areas=["problem"], approved_by="user:shubham",
        actor_id="user:shubham", session_id="sess-review", now=NOW,
    )
    first = current_review_approval(project.events_path)
    assert first is not None
    assert first.approved_areas == ["problem"]

    grant_review_approval(
        project.events_path, approved_areas=["problem", "users", "jobs"], approved_by="user:shubham",
        actor_id="user:shubham", session_id="sess-review", now=NOW,
    )
    second = current_review_approval(project.events_path)
    assert second is not None
    assert second.approved_areas == ["problem", "users", "jobs"]


def test_no_agent_is_ever_granted_a_tool_to_approve_its_own_review():
    """`grant_review_approval` is a plain function, never registered as an
    MCP tool — mirroring T18's own rule for Linear-issue approval. Asserted
    here by checking the real tool registry has no such entry, not just by
    reading the docstring."""

    from ppa.tools.registry import get

    with pytest.raises(KeyError):
        get("approve_review")


# ---------------------------------------------------------------------------
# One real REVIEW turn — presenting and walking assumptions is the model's
# own job, proven live.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_a_real_review_turn_walks_assumptions_individually(tmp_path):
    project = _make_project(tmp_path)
    asm_a = _seed_high_assumption(project, "Payments settle in USD only for v1")
    asm_b = _seed_high_assumption(project, "Only one approver is needed per invoice, regardless of amount")

    entities_before = current_entities(project.events_path)
    high_proposed_before = {eid: e for eid, e in entities_before.items() if getattr(e, "impact", None) == "HIGH" and e.status == "PROPOSED"}
    assert set(high_proposed_before) == {asm_a, asm_b}

    user_message = (
        "Walk this review now. Both assumptions below are reasonable for a first version — confirm "
        f"{asm_a} as stated, and confirm {asm_b} as stated too. Then ask for my approval."
    )
    result = run_review_session(project, user_message=user_message)
    assert result.status.value == "OK", result.summary

    entities_after = current_entities(project.events_path)
    report = evaluate_review_round(high_proposed_before, entities_after)
    assert report.ok, (report.violations, result.summary)
