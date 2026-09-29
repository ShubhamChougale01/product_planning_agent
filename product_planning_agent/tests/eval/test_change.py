"""T30 eval — change handling: detect, surface, supersede, impact, rewind.

Detection (T11, already built), surfacing/recording a verdict
(`manage_conflict`), superseding, impact analysis (T11) and the workflow
rewind are all mechanical — proven directly, no model needed. Adjudicating
*which* verdict a real contradiction deserves, and actually narrating it
rather than silently appending, is the model's own job, proven live once in
`test_a_real_change_turn_surfaces_a_genuine_contradiction` (marked
`live_model`).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.agents.modes.change import evaluate_change_handling, run_change_session, unresolved_conflicts_from_events
from ppa.config.profiles import UserProfile
from ppa.engines.conflicts import find_conflict_candidates
from ppa.engines.impact import analyze_impact
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.ledger.store import read_project_meta, write_project_meta
from ppa.tools.approval import _read_all_events
from ppa.tools.discovery_tools import manage_conflict, manage_requirement
from ppa.tools.interaction import ask_user

NOW = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="product", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Change Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-change", now=NOW)
    base.update(overrides)
    return base


def _seed_confirmed_requirement(project, *, statement: str, area: str = "scope_in") -> str:
    answered = ask_user(
        [{"text": "What's the initial scope?", "why_asked": "seeds the fixture", "answer": {"answer_kind": "answered", "answer_text": statement}}],
        project, **_writer_kwargs(),
    )
    assert answered.success is True, answered.error
    answer_id = answered.data[0]["answer_id"]

    req = manage_requirement(
        "create", project, **_writer_kwargs(),
        statement=statement, type="functional", priority="must", confidence="HIGH",
        confidence_basis="directly stated by the user", covers_areas=[area], derived_from_answers=[answer_id],
    )
    assert req.success is True, req.error
    req_id = req.data["entity_id"]
    confirmed = manage_requirement("confirm", project, **_writer_kwargs(), entity_id=req_id)
    assert confirmed.success is True, confirmed.error
    return req_id


# ---------------------------------------------------------------------------
# Done when: the contradicts_self persona's conflict is surfaced, not
# silently appended; superseded entities keep history.
# ---------------------------------------------------------------------------


def test_contradiction_is_detected_against_the_confirmed_requirement(tmp_path):
    project = _make_project(tmp_path)
    _seed_confirmed_requirement(project, statement="Internal tool, ~20 users, no public access")

    answered = ask_user(
        [{"text": "Anything changed?", "why_asked": "change request", "answer": {"answer_kind": "answered", "answer_text": "Actually we want a public launch, open to anyone"}}],
        project, **_writer_kwargs(),
    )
    assert answered.success is True, answered.error
    answer_id = answered.data[0]["answer_id"]

    entities = current_entities(project.events_path)
    answer = entities[answer_id]
    candidates = find_conflict_candidates(answer, entities)
    assert len(candidates) == 1


def test_an_unadjudicated_contradiction_fails_the_shape_contract(tmp_path):
    project = _make_project(tmp_path)
    req_id = _seed_confirmed_requirement(project, statement="Internal tool, ~20 users, no public access")

    entities_before = current_entities(project.events_path)
    answered = ask_user(
        [{"text": "Anything changed?", "why_asked": "change request", "answer": {"answer_kind": "answered", "answer_text": "Actually we want a public launch"}}],
        project, **_writer_kwargs(),
    )
    answer_id = answered.data[0]["answer_id"]
    entities = current_entities(project.events_path)
    candidate = find_conflict_candidates(entities[answer_id], entities)[0]

    entities_after = current_entities(project.events_path)  # no adjudication happened — silently dropped
    report = evaluate_change_handling(entities_before, entities_after, project.events_path, watched_candidate=candidate)
    assert not report.ok
    assert any("silently dropped" in v for v in report.violations)


def test_surfacing_then_superseding_resolves_a_contradiction_and_keeps_history(tmp_path):
    project = _make_project(tmp_path)
    req_id = _seed_confirmed_requirement(project, statement="Internal tool, ~20 users, no public access")

    entities_before = current_entities(project.events_path)
    answered = ask_user(
        [{"text": "Anything changed?", "why_asked": "change request", "answer": {"answer_kind": "answered", "answer_text": "Actually we want a public launch"}}],
        project, **_writer_kwargs(),
    )
    answer_id = answered.data[0]["answer_id"]
    entities = current_entities(project.events_path)
    candidate = find_conflict_candidates(entities[answer_id], entities)[0]

    # Step 3 — surface it, not yet resolved.
    surfaced = manage_conflict(
        "adjudicate", project, **_writer_kwargs(),
        subject_id=candidate.subject_id, candidate_id=candidate.candidate_id, verdict="contradiction",
        resolved=False, explanation="internal-tool phrasing directly contradicts a public launch",
    )
    assert surfaced.success is True, surfaced.error
    assert unresolved_conflicts_from_events(project.events_path)

    # Step 4 — supersede the old requirement, create its replacement.
    superseded = manage_requirement("supersede", project, **_writer_kwargs(), entity_id=req_id, change_reason="user confirmed a public launch, contradicting the internal-only scope")
    assert superseded.success is True, superseded.error
    new_req = manage_requirement(
        "create", project, **_writer_kwargs(),
        statement="Public launch, open to anyone", type="functional", priority="must", confidence="HIGH",
        confidence_basis="user confirmed directly", covers_areas=["scope_in"], derived_from_answers=[answer_id],
    )
    assert new_req.success is True, new_req.error

    # Re-adjudicate, now resolved.
    resolved = manage_conflict(
        "adjudicate", project, **_writer_kwargs(),
        subject_id=candidate.subject_id, candidate_id=candidate.candidate_id, verdict="contradiction",
        resolved=True, explanation="resolved by superseding REQ with the public-launch version",
    )
    assert resolved.success is True, resolved.error

    entities_after = current_entities(project.events_path)
    assert not unresolved_conflicts_from_events(project.events_path)
    assert entities_after[req_id].status == "SUPERSEDED"
    assert entities_after[req_id].statement == "Internal tool, ~20 users, no public access"  # history intact, never mutated

    report = evaluate_change_handling(entities_before, entities_after, project.events_path, watched_candidate=candidate)
    assert report.ok, report.violations
    assert report.superseded_count >= 1

    # Step 5 — impact naming affected entities (even if empty, the report itself must exist and be well-formed).
    impact = analyze_impact(req_id, entities_after)
    assert impact.source_entity_id == req_id


# ---------------------------------------------------------------------------
# Done when: readiness gate condition 6 (unresolved conflicts).
# ---------------------------------------------------------------------------


def test_an_unresolved_contradiction_blocks_readiness_via_condition_six(tmp_path):
    project = _make_project(tmp_path)
    _seed_confirmed_requirement(project, statement="Internal tool, ~20 users, no public access")
    answered = ask_user(
        [{"text": "Anything changed?", "why_asked": "change request", "answer": {"answer_kind": "answered", "answer_text": "Actually we want a public launch"}}],
        project, **_writer_kwargs(),
    )
    answer_id = answered.data[0]["answer_id"]
    entities = current_entities(project.events_path)
    candidate = find_conflict_candidates(entities[answer_id], entities)[0]

    manage_conflict(
        "adjudicate", project, **_writer_kwargs(),
        subject_id=candidate.subject_id, candidate_id=candidate.candidate_id, verdict="contradiction",
        resolved=False, explanation="surfaced, not yet resolved",
    )

    unresolved = unresolved_conflicts_from_events(project.events_path)
    entities = current_entities(project.events_path)
    _ready, blockers = check_readiness(entities, _profile(), unresolved_conflicts=unresolved)
    assert any(b.condition == "unresolved_conflict" for b in blockers)


# ---------------------------------------------------------------------------
# Done when: the change produces an impact report naming affected entities;
# the gate drops back to NOT READY and the workflow rewinds.
# ---------------------------------------------------------------------------


def test_workflow_rewinds_from_change_requested_to_discovery(tmp_path):
    from ppa.agents.modes.change import REWIND_TARGET, _rewind_workflow

    project = _make_project(tmp_path)
    meta = read_project_meta(project.events_path)
    meta["workflow_state"] = "DISCOVERY_VALIDATED"
    write_project_meta(project.events_path, meta)

    target = _rewind_workflow(project, workflow_state="DISCOVERY_VALIDATED")
    assert target == REWIND_TARGET == "DISCOVERY"

    meta_after = read_project_meta(project.events_path)
    assert meta_after["workflow_state"] == "DISCOVERY"


# ---------------------------------------------------------------------------
# One real change-handling turn — adjudication is the model's own job,
# proven live.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_a_real_change_turn_surfaces_a_genuine_contradiction(tmp_path):
    project = _make_project(tmp_path)
    req_id = _seed_confirmed_requirement(project, statement="This is strictly an internal tool for our own accounting team, about 20 users, never public")

    result = run_change_session(
        project, change_text="Actually, we've decided this needs to be a public launch open to anyone who signs up.",
        actor_id="user:shubham", session_id="sess-change-live",
    )
    assert result.status.value == "OK", result.summary
    assert result.data["rewound_to"] == "DISCOVERY"

    unresolved_or_resolved = [
        e.after for e in _read_all_events(project.events_path)
        if e.type.value == "conflict.adjudicated"
    ]
    assert unresolved_or_resolved, "the model never adjudicated the contradiction at all"
    assert any(a["subject_id"] == req_id for a in unresolved_or_resolved)
