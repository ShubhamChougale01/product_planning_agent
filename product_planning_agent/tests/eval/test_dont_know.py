"""T26 eval — the don't-know routing table, checked two ways.

Classification (matching a raw "I don't know" signal to one of seven
kinds) is the model's own job, guided by `mode_clarify.md`'s table — proven
live, once, in `test_a_real_clarify_turn_classifies_and_routes_all_seven_
kinds` below (marked `live_model`, excluded from the default run). Every
kind's *routing* (does `no_opinion` actually produce an Assumption with
`user_confirmation_required`?) is mechanical once the kind is known, and is
proven directly against the real `manage_*` writers with no model involved
at all — the same split `ppa.engines.question_engine` already draws between
deterministic scoring and the model's own qualitative filter.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone

import anyio
import pytest

from ppa.agents.discovery import DiscoveryMode, allowed_tools_for_mode, render_system_prompt
from ppa.agents.modes.dont_know import evaluate_dont_know_routing
from ppa.agents.turn import _mode_scoped_server_and_allowed_tools, _run_one_sdk_turn, _tool_discovery_hint
from ppa.config.profiles import UserProfile
from ppa.engines.dont_know_classifier import (
    DONT_KNOW_KINDS,
    EXPENSIVE_KINDS,
    MAX_REFRAME_ATTEMPTS,
    ROUTE_FOR_KIND,
    SIGNAL_EXAMPLES,
    is_same_question,
    should_force_escalation,
    simulate_always_idk_termination,
)
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import create_project
from ppa.ledger.store import read_project_meta, write_project_meta
from ppa.tools.discovery_tools import manage_assumption, manage_decision, manage_unknown
from ppa.tools.interaction import ask_user

NOW = datetime(2026, 9, 28, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Dont Know Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-dont-know", now=NOW)
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ppa.engines.dont_know_classifier — pure, deterministic, no model.
# ---------------------------------------------------------------------------


def test_seven_kinds_are_named_and_routed():
    assert len(DONT_KNOW_KINDS) == 7
    assert set(ROUTE_FOR_KIND) == set(DONT_KNOW_KINDS)
    assert set(SIGNAL_EXAMPLES) == set(DONT_KNOW_KINDS)


def test_only_unexplored_and_factually_unknown_are_expensive():
    assert EXPENSIVE_KINDS == {"unexplored", "factually_unknown"}
    assert "dont_understand" not in EXPENSIVE_KINDS


def test_should_force_escalation_fires_after_max_reframe_attempts():
    assert should_force_escalation(MAX_REFRAME_ATTEMPTS) is True
    assert should_force_escalation(MAX_REFRAME_ATTEMPTS - 1) is False
    assert should_force_escalation(0) is False


def test_is_same_question_ignores_case_and_whitespace_only():
    assert is_same_question("Who approves refunds?", "who approves refunds?") is True
    assert is_same_question("Who approves refunds?", "  Who   approves refunds?  ") is True
    assert is_same_question("Who approves refunds?", "Who signs off on refunds?") is False


def test_always_idk_persona_terminates_without_repeating_a_question():
    """S8.3: bounded number of asks, never an unbounded loop — see the
    function's own docstring for why this is a deterministic proof of the
    engine's arithmetic, not a substitute for T33/T34's own persona-driven
    session (blockers.md decision logged against this exact gap)."""

    asked = simulate_always_idk_termination()
    assert len(asked) == MAX_REFRAME_ATTEMPTS + 1
    assert len(set(a.lower() for a in asked)) == len(asked)


# ---------------------------------------------------------------------------
# ppa.agents.modes.dont_know — routing -> entity shape, direct writer calls.
# ---------------------------------------------------------------------------


def test_no_opinion_produces_an_assumption_requiring_confirmation(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    result = manage_assumption(
        "create", project, **_writer_kwargs(),
        statement="Assume standard 30-day payment terms unless told otherwise",
        reason="user said 'whatever you think is best' when asked about payment terms",
        impact="MEDIUM", confidence="LOW", confidence_basis="no_opinion default, unconfirmed",
    )
    assert result.success is True, result.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("no_opinion", before, after)
    assert report.ok, report.violations


def test_manage_assumption_spec_exposes_provisional_to_the_model():
    """Bug #13 (blockers.md): `provisional` was handled by `_assumption_
    create` but never listed in `MANAGE_ASSUMPTION_SPEC.inputs`/`optional`
    — the SDK schema (`ppa.tools.server._sdk_input_schema`) is built purely
    from those two, so a real model call had no way to ever set it. Found
    live: `needs_external_input` consistently created an unflagged
    Assumption until this was fixed."""

    from ppa.tools.discovery_tools import MANAGE_ASSUMPTION_SPEC

    assert "provisional" in MANAGE_ASSUMPTION_SPEC.inputs
    assert "provisional" in MANAGE_ASSUMPTION_SPEC.optional


def test_needs_external_input_produces_a_provisional_assumption(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    result = manage_assumption(
        "create", project, **_writer_kwargs(),
        statement="Assume the client's existing SSO covers this until they confirm",
        reason="user said 'that's the client's call, not mine' when asked about auth",
        impact="MEDIUM", confidence="LOW", confidence_basis="pending external confirmation",
        provisional=True,
    )
    assert result.success is True, result.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("needs_external_input", before, after)
    assert report.ok, report.violations


def test_not_my_call_produces_a_decision_with_owner_not_the_user(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    opened = manage_decision(
        "open", project, **_writer_kwargs(),
        question="What pricing model do we use?", owner="role:cto", owner_type="agent",
    )
    assert opened.success is True, opened.error
    dec_id = opened.data["entity_id"]

    deferred = manage_decision(
        "defer", project, **_writer_kwargs(), entity_id=dec_id,
        defer_reason="user said this is the CTO's decision, not theirs",
        owner="role:cto", owner_type="agent",
    )
    assert deferred.success is True, deferred.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("not_my_call", before, after)
    assert report.ok, report.violations


def test_factually_unknown_produces_an_unknown_routed_to_research(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="Which database scales better for this workload?", area="platform",
        why_it_matters="shapes the data layer architecture", blocking=False,
        route="RESEARCH", owner_type="agent",
    )
    assert result.success is True, result.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("factually_unknown", before, after)
    assert report.ok, report.violations


def test_a_blocking_research_item_is_recorded_blocking_and_routed_research(tmp_path):
    """The case a single `classification` enum could not express (T02) —
    blocking and RESEARCH are independent fields."""

    project = _make_project(tmp_path)
    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="Which auth model shapes our scope here?", area="nfr",
        why_it_matters="determines whether SSO is in scope for v1", blocking=True,
        route="RESEARCH", owner_type="agent",
    )
    assert result.success is True, result.error

    entities = current_entities(project.events_path)
    unk = entities[result.data["entity_id"]]
    assert unk.blocking is True
    assert unk.route == "RESEARCH"


def test_depends_on_x_records_the_dependency_as_a_user_decision_unknown(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="What's the budget? (blocks: which hosting tier to target)", area="platform",
        why_it_matters="the hosting tier question can't be answered until the budget is known",
        blocking=False, route="USER_DECISION", owner_type="user",
    )
    assert result.success is True, result.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("depends_on_x", before, after)
    assert report.ok, report.violations


def test_unexplored_routes_to_guidance_as_a_blocking_unknown(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="Who is the target user, really?", area="users",
        why_it_matters="user said they haven't thought about it — needs full Guidance Mode",
        blocking=True, route="GUIDANCE", owner_type="agent",
    )
    assert result.success is True, result.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("unexplored", before, after)
    assert report.ok, report.violations


def test_dont_understand_reframes_via_ask_user_and_triggers_no_research(tmp_path):
    """`dont_understand` never triggers research — the research provider
    (`ppa.providers.research`, still an empty stub until T29) has nothing to
    spy on yet, so this asserts the structural proxy available today: no
    Unknown(route=RESEARCH) or ResearchFinding results from this kind."""

    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    original = ask_user(
        [{"text": "Who approves refunds?", "why_asked": "affects the approval workflow"}],
        project, **_writer_kwargs(),
    )
    assert original.success is True, original.error

    reframed = ask_user(
        [{
            "text": "When a customer asks for money back, whose sign-off do you need before it happens?",
            "why_asked": "reframing — the original phrasing wasn't clear",
        }],
        project, **_writer_kwargs(),
    )
    assert reframed.success is True, reframed.error

    after = current_entities(project.events_path)
    report = evaluate_dont_know_routing("dont_understand", before, after)
    assert report.ok, report.violations


def test_no_question_is_ever_re_asked_in_identical_form(tmp_path):
    project = _make_project(tmp_path)

    first = ask_user(
        [{"text": "Who approves refunds?", "why_asked": "affects the approval workflow"}],
        project, **_writer_kwargs(),
    )
    assert first.success is True, first.error

    entities = current_entities(project.events_path)
    prior_texts = [e.text for eid, e in entities.items() if entity_type_for(eid) is EntityType.QUESTION_ANSWER]

    reframed_text = "When a customer asks for money back, whose sign-off do you need first?"
    assert not any(is_same_question(reframed_text, prior) for prior in prior_texts)

    verbatim_repeat = "Who approves refunds?"
    assert any(is_same_question(verbatim_repeat, prior) for prior in prior_texts)


# ---------------------------------------------------------------------------
# One real Clarify turn — classification is the model's job, proven live.
# ---------------------------------------------------------------------------


def _seed_pending_questions(project) -> dict[str, str]:
    """Seven `Q-nnn`, one per kind, each still `PENDING` — mirroring what a
    real prior CLARIFY round would have asked. Returns `{kind: question_id}`."""

    topic_by_kind = {
        "dont_understand": "Who approves refunds?",
        "no_opinion": "What payment terms should invoices default to?",
        "depends_on_x": "Which hosting tier should we target?",
        "not_my_call": "What pricing model should we use?",
        "unexplored": "Who is the target user, exactly?",
        "factually_unknown": "Which database scales better for this workload?",
        "needs_external_input": "What auth method should we integrate with?",
    }
    ids: dict[str, str] = {}
    for kind, text in topic_by_kind.items():
        result = ask_user([{"text": text, "why_asked": "scoping this area"}], project, **_writer_kwargs())
        assert result.success is True, result.error
        ids[kind] = result.data[0]["question_id"]
    return ids


@pytest.mark.live_model
def test_a_real_clarify_turn_classifies_and_routes_all_seven_kinds(tmp_path):
    project = _make_project(tmp_path)
    question_ids = _seed_pending_questions(project)

    meta = read_project_meta(project.events_path)
    meta["discovery_mode"] = DiscoveryMode.CLARIFY.value
    write_project_meta(project.events_path, meta)

    entities_before = current_entities(project.events_path)

    server, allowed_tools = _mode_scoped_server_and_allowed_tools(DiscoveryMode.CLARIFY, project)
    system_prompt = _tool_discovery_hint(allowed_tools) + "\n\n" + render_system_prompt(
        DiscoveryMode.CLARIFY, project.profile, today=NOW.date(),
    )

    user_message = (
        "You previously asked seven open questions this project. The person just replied to all "
        "seven at once — here is each question's id and their literal reply:\n\n"
        + "\n".join(f'- {qid}: "{SIGNAL_EXAMPLES[kind]}"' for kind, qid in question_ids.items())
        + "\n\nProcess every one of these seven replies now: classify which of the seven \"I don't "
        "know\" kinds each reply actually is, and route it using the table in your own mode "
        "instructions. Call the tools for real — do not just narrate what you would do."
    )

    text, _cost = anyio.run(
        functools.partial(
            _run_one_sdk_turn,
            system_prompt=system_prompt, server=server, allowed_tools=allowed_tools, user_message=user_message,
        )
    )
    assert text

    entities_after = current_entities(project.events_path)
    new_assumptions = {
        eid: e for eid, e in entities_after.items() if eid not in entities_before and entity_type_for(eid) is EntityType.ASSUMPTION
    }
    new_decisions = {
        eid: e for eid, e in entities_after.items()
        if entity_type_for(eid) is EntityType.DECISION and (eid not in entities_before or entities_before[eid] != e)
    }
    new_unknowns = {
        eid: e for eid, e in entities_after.items() if eid not in entities_before and entity_type_for(eid) is EntityType.UNKNOWN
    }
    new_questions = {
        eid: e for eid, e in entities_after.items() if eid not in entities_before and entity_type_for(eid) is EntityType.QUESTION_ANSWER
    }

    violations: list[str] = []
    if not any(a.user_confirmation_required and not a.provisional for a in new_assumptions.values()):
        violations.append("no_opinion: expected an unconditional Assumption")
    if not any(a.provisional and a.user_confirmation_required for a in new_assumptions.values()):
        violations.append("needs_external_input: expected a provisional Assumption")
    if not any(d.owner_type != "user" and d.status == "DECIDE_LATER" for d in new_decisions.values()):
        violations.append("not_my_call: expected a deferred Decision with owner_type != user")
    if not any(u.route == "RESEARCH" for u in new_unknowns.values()):
        violations.append("factually_unknown: expected an Unknown routed to RESEARCH")
    if not any(u.route == "GUIDANCE" and u.blocking for u in new_unknowns.values()):
        violations.append("unexplored: expected a blocking Unknown routed to GUIDANCE")
    if not any(u.route == "USER_DECISION" for u in new_unknowns.values()):
        violations.append("depends_on_x: expected an Unknown routed to USER_DECISION")
    if not any(q.status == "PENDING" for q in new_questions.values()):
        violations.append("dont_understand: expected a reframed, still-PENDING question")

    assert not violations, (violations, text)
