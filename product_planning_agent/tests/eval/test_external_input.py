"""T27 eval — external-input routing and the client questionnaire.

Routing (`needs_external_input`'s three-call sequence: an external-owned
Unknown, a provisional Assumption, the `converted_to` link between them) is
mechanical once the kind is known — proven directly against the real
`manage_*` writers, no model involved, the same split T26's own eval draws.
Classification (recognizing "that's the client's call" as this kind) is the
model's job, guided by `mode_clarify.md`, proven live once, in
`test_a_real_clarify_turn_routes_needs_external_input` (marked
`live_model`, excluded from the default run).
"""

from __future__ import annotations

import functools
import re
from datetime import datetime, timezone

import anyio
import pytest

from ppa.agents.discovery import DiscoveryMode, render_system_prompt
from ppa.agents.modes.external import evaluate_external_input_round
from ppa.agents.turn import _mode_scoped_server_and_allowed_tools, _run_one_sdk_turn, _tool_discovery_hint
from ppa.config.areas import AREAS
from ppa.config.house_style import load_house_style
from ppa.config.profiles import UserProfile, critical_areas
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.ledger.store import read_project_meta, write_project_meta
from ppa.render.client_questions import render_client_questionnaire
from ppa.tools.discovery_tools import manage_assumption, manage_requirement, manage_unknown
from ppa.tools.interaction import ask_user

_AREA_LABELS = {area.key: area.label for area in AREAS}

NOW = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="product", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="External Input Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-external", now=NOW)
    base.update(overrides)
    return base


def _route_needs_external_input(project, *, area: str, question: str, why_it_matters: str, blocking: bool, statement: str, reason: str):
    """The three-call sequence `mode_clarify.md` now instructs for
    `needs_external_input` — exercised directly, no model."""

    unk = manage_unknown(
        "record", project, **_writer_kwargs(),
        question=question, area=area, why_it_matters=why_it_matters, blocking=blocking,
        route="ASSUMPTION", owner_type="external",
    )
    assert unk.success is True, unk.error
    unk_id = unk.data["entity_id"]

    asm = manage_assumption(
        "create", project, **_writer_kwargs(),
        statement=statement, reason=reason, impact="MEDIUM", confidence="LOW",
        confidence_basis="pending external confirmation", provisional=True,
    )
    assert asm.success is True, asm.error
    asm_id = asm.data["entity_id"]

    converted = manage_unknown(
        "convert", project, **_writer_kwargs(), entity_id=unk_id, converted_to=asm_id,
    )
    assert converted.success is True, converted.error
    return unk_id, asm_id


# ---------------------------------------------------------------------------
# ppa.agents.modes.external — routing -> entity shape, direct writer calls.
# ---------------------------------------------------------------------------


def test_needs_external_input_produces_a_linked_open_item_and_assumption(tmp_path):
    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    _route_needs_external_input(
        project, area="nfr", question="What auth method should we integrate with?",
        why_it_matters="determines whether SSO is in scope for this rollout", blocking=False,
        statement="Assume the client's existing SSO covers this until they confirm",
        reason="user said 'that's the client's call, not mine' when asked about auth",
    )

    after = current_entities(project.events_path)
    report = evaluate_external_input_round(before, after)
    assert report.ok, report.violations
    assert report.open_item_count == 1
    assert report.linked_to_provisional_assumption_count == 1


def test_unlinked_external_item_is_flagged_as_a_violation(tmp_path):
    """`converted_to` is never optional — an open item that never got its
    provisional assumption linked has nothing to show as "what we'll assume
    until you confirm," so the shape contract must catch it."""

    project = _make_project(tmp_path)
    before = current_entities(project.events_path)

    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="What pricing model should we use?", area="scope_in",
        why_it_matters="shapes the billing integration", blocking=False,
        route="ASSUMPTION", owner_type="external",
    )
    assert result.success is True, result.error

    after = current_entities(project.events_path)
    report = evaluate_external_input_round(before, after)
    assert not report.ok
    assert any("no converted_to" in v for v in report.violations)


# ---------------------------------------------------------------------------
# Done when: a session where the user says "that's the client's call" three
# times produces a sendable questionnaire.
# ---------------------------------------------------------------------------


def test_three_external_answers_produce_a_grouped_client_questionnaire(tmp_path):
    project = _make_project(tmp_path)

    _route_needs_external_input(
        project, area="nfr", question="What auth method should we integrate with?",
        why_it_matters="determines whether SSO is in scope for this rollout", blocking=True,
        statement="Assume the client's existing SSO covers this until they confirm",
        reason="user said 'that's the client's call' when asked about auth",
    )
    _route_needs_external_input(
        project, area="scope_in", question="What pricing model should we use?",
        why_it_matters="shapes the billing integration we build", blocking=False,
        statement="Assume a flat monthly subscription until they confirm",
        reason="user said 'that's the client's call' when asked about pricing",
    )
    _route_needs_external_input(
        project, area="nfr", question="Which compliance regime applies (SOC2, HIPAA, neither)?",
        why_it_matters="determines what audit logging we must ship on day one", blocking=False,
        statement="Assume no special compliance regime until they confirm",
        reason="user said 'that's the client's call' when asked about compliance",
    )

    entities = current_entities(project.events_path)
    style = load_house_style()
    doc = render_client_questionnaire(entities, style)

    assert doc.count("### ") == 3
    # AREA_KEYS declares scope_in before nfr — the questionnaire must follow
    # that same order, not creation order or alphabetical order.
    assert doc.index(f"## {_AREA_LABELS['scope_in']}") < doc.index(f"## {_AREA_LABELS['nfr']}")
    assert "SSO covers this until they confirm" in doc
    assert "flat monthly subscription" in doc
    assert "Blocking:** Yes" in doc
    assert "Blocking:** No" in doc


def test_questionnaire_is_free_of_internal_jargon_and_entity_ids(tmp_path):
    project = _make_project(tmp_path)
    _route_needs_external_input(
        project, area="platform", question="Which cloud provider should we deploy to?",
        why_it_matters="shapes the infrastructure we build against", blocking=False,
        statement="Assume AWS until they confirm", reason="user deferred to the client",
    )

    entities = current_entities(project.events_path)
    doc = render_client_questionnaire(entities, load_house_style())

    assert not re.search(r"\b(UNK|ASM|DEC|REQ|Q|ANS|RES)-\d+\b", doc)
    for jargon in ("owner_type", "route=", "blocking=True", "blocking=False", "PROPOSED", "CONFIRMED"):
        assert jargon not in doc


def test_questionnaire_with_no_open_items_says_so_plainly(tmp_path):
    project = _make_project(tmp_path)
    doc = render_client_questionnaire(current_entities(project.events_path), load_house_style())
    assert "No open questions for you right now." in doc


def test_ppa_client_questions_renders_markdown_and_honours_house_style(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = create_project("CLI External Project", "seed requirement", _profile(), projects_root=tmp_path / "projects")
    _route_needs_external_input(
        project, area="data", question="Which analytics provider should we send events to?",
        why_it_matters="shapes the event-tracking integration", blocking=False,
        statement="Assume no analytics provider until they confirm", reason="client's call",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["client-questions", project.slug])

    assert result.exit_code == 0, result.output
    assert "# " in result.output and "## " in result.output
    assert "analytics provider" in result.output
    style = load_house_style()
    assert style.name.replace("_", " ").title() in result.output


# ---------------------------------------------------------------------------
# Done when: external-owned blocking items do not block READY.
# ---------------------------------------------------------------------------


def test_external_owned_blocking_unknown_does_not_block_readiness(tmp_path):
    project = _make_project(tmp_path)
    profile = _profile(role="product")

    # A real answer to derive every fixture requirement from — manage_
    # requirement(create) rejects anything with no provenance link.
    answered = ask_user(
        [{
            "text": "What must this system do, at minimum?", "why_asked": "seeds the fixture requirements",
            "answer": {"answer_kind": "answered", "answer_text": "cover every critical area"},
        }],
        project, **_writer_kwargs(),
    )
    assert answered.success is True, answered.error
    answer_id = answered.data[0]["answer_id"]

    # Cover every critical area for a `product` profile with a CONFIRMED
    # requirement, so the only thing standing between this ledger and READY
    # is the one Unknown this test cares about.
    for area in sorted(critical_areas(profile)):
        req = manage_requirement(
            "create", project, **_writer_kwargs(),
            statement=f"Requirement covering {area}", covers_areas=[area], priority="must",
            type="functional", confidence="HIGH", confidence_basis="directly stated by the user",
            derived_from_answers=[answer_id],
        )
        assert req.success is True, req.error
        confirmed = manage_requirement(
            "confirm", project, **_writer_kwargs(), entity_id=req.data["entity_id"],
        )
        assert confirmed.success is True, confirmed.error

    _route_needs_external_input(
        project, area=sorted(critical_areas(profile))[0], question="What pricing model should we use?",
        why_it_matters="shapes billing", blocking=True,
        statement="Assume a flat subscription until they confirm", reason="client's call",
    )

    entities = current_entities(project.events_path)
    ready, blockers = check_readiness(entities, profile, confirmed_areas=set(critical_areas(profile)))
    blocking_unknown_blockers = [b for b in blockers if b.condition == "blocking_unknown"]
    assert not blocking_unknown_blockers, blockers


# ---------------------------------------------------------------------------
# One real Clarify turn — classification is the model's job, proven live.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_a_real_clarify_turn_routes_needs_external_input(tmp_path):
    project = _make_project(tmp_path)

    asked = ask_user(
        [{"text": "Which payment gateway should we integrate with?", "why_asked": "determines the billing integration"}],
        project, **_writer_kwargs(),
    )
    assert asked.success is True, asked.error
    question_id = asked.data[0]["question_id"]

    meta = read_project_meta(project.events_path)
    meta["discovery_mode"] = DiscoveryMode.CLARIFY.value
    write_project_meta(project.events_path, meta)

    entities_before = current_entities(project.events_path)

    server, allowed_tools = _mode_scoped_server_and_allowed_tools(DiscoveryMode.CLARIFY, project)
    system_prompt = _tool_discovery_hint(allowed_tools) + "\n\n" + render_system_prompt(
        DiscoveryMode.CLARIFY, project.profile, today=NOW.date(),
    )

    user_message = (
        f"You previously asked one open question this project — {question_id}: "
        '"Which payment gateway should we integrate with?" The person just replied: '
        '"That\'s the client\'s call, not mine." Classify this "I don\'t know" and route it using '
        "the table in your own mode instructions. Call the tools for real — do not just narrate "
        "what you would do."
    )

    text, _cost = anyio.run(
        functools.partial(
            _run_one_sdk_turn,
            system_prompt=system_prompt, server=server, allowed_tools=allowed_tools, user_message=user_message,
        )
    )
    assert text

    entities_after = current_entities(project.events_path)
    report = evaluate_external_input_round(entities_before, entities_after)
    assert report.ok, (report.violations, text)
