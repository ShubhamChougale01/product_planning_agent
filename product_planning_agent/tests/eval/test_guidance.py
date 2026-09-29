"""T28 eval — the Guidance Mode subagent.

Schema validation, rendering, persistence-linking and the DECIDE_LATER +
safe-default-ASM "landing" sequence are all mechanical once a brief exists
— proven directly, no model involved. Producing the brief itself (steps
1-6 of DESIGN.md S3.5's sequence, including real web research) is the
model's own job, proven live once in `test_a_real_guidance_session_
produces_a_schema_valid_brief_and_persists_it` (marked `live_model`).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ppa.agents.registry import GRANTS
from ppa.agents.subagents.guidance import (
    MIN_OPTIONS,
    GuidanceBrief,
    _guidance_server_and_allowed_tools,
    parse_guidance_brief,
    run_guidance_session,
)
from ppa.config.profiles import UserProfile
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import create_project
from ppa.render.guidance_card import render_guidance_brief, render_why
from ppa.tools.discovery_tools import manage_assumption, manage_decision, manage_research, manage_unknown

_BRIEF_JSON = """
{
  "dont_know_kind": "unexplored",
  "restated_plainly": "When someone opens this app, are they managing their own invoices or someone else's on a team's behalf?",
  "why_it_matters": "It decides whether we need a permissions model at all for v1, or a single-user flow.",
  "what_it_affects": ["users", "scope_in"],
  "options": [
    {"name": "Single-user", "description": "One person, one account, no sharing.", "pros": ["Much less to build"], "cons": ["Blocks any team use case"], "best_when": "The target is a solo freelancer or small owner-operator."},
    {"name": "Team with roles", "description": "Multiple users per account, with an approver role.", "pros": ["Matches how invoices actually get approved at a company"], "cons": ["Needs a permissions model in v1"], "best_when": "The target is a small business with a bookkeeper and an owner."}
  ],
  "recommendation": {"option": "Team with roles", "because": "The seed requirement mentions 'vendor invoice tracking', which is a team accounting function, not a personal one.", "confidence": "MEDIUM"},
  "what_would_settle_it": "Ask directly: will more than one person at the client ever need to log in?",
  "safe_default_if_deferred": "Build single-user for v1, with the data model shaped so a role can be added later without a rewrite.",
  "researched": false,
  "sources": []
}
"""


def _profile(**overrides) -> UserProfile:
    base = dict(role="product", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Guidance Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-guidance")
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Done when: schema-valid GuidanceBrief with >=2 options and a recommendation.
# ---------------------------------------------------------------------------


def test_guidance_brief_parses_from_the_models_own_reply_shape():
    brief = parse_guidance_brief(_BRIEF_JSON)
    assert len(brief.options) >= MIN_OPTIONS
    assert brief.recommendation.option == "Team with roles"
    assert brief.recommendation.confidence in ("HIGH", "MEDIUM", "LOW")


def test_guidance_brief_tolerates_a_markdown_fence_the_model_added_anyway():
    fenced = "```json\n" + _BRIEF_JSON.strip() + "\n```"
    brief = parse_guidance_brief(fenced)
    assert brief.restated_plainly


def test_guidance_brief_rejects_fewer_than_two_options():
    import json

    data = json.loads(_BRIEF_JSON)
    data["options"] = data["options"][:1]
    with pytest.raises(ValidationError):
        GuidanceBrief.model_validate(data)


# ---------------------------------------------------------------------------
# Done when: rendered output reads like a colleague — no raw JSON.
# ---------------------------------------------------------------------------


def test_rendered_brief_has_no_raw_json_and_reads_as_prose():
    brief = parse_guidance_brief(_BRIEF_JSON)
    rendered = render_guidance_brief(brief)

    assert "{" not in rendered and "}" not in rendered
    assert '"dont_know_kind"' not in rendered
    assert "Team with roles" in rendered
    assert "medium confidence" in rendered
    assert "Single-user" in rendered


# ---------------------------------------------------------------------------
# Done when: the brief persists as RES-nnn linked to the resulting DEC-nnn,
# and `ppa why <dec-id>` can answer from the ledger alone.
# ---------------------------------------------------------------------------


def test_research_finding_links_to_its_decision_and_why_reads_it_back(tmp_path):
    project = _make_project(tmp_path)
    brief = parse_guidance_brief(_BRIEF_JSON)

    res = manage_research(
        "create", project, **_writer_kwargs(agent_id="guidance"),
        question=brief.restated_plainly, method="reasoning from the ledger's own context",
        summary=f"{brief.recommendation.option} — {brief.recommendation.because}",
        options_found=[o.name for o in brief.options], sources=brief.sources,
        confidence=brief.recommendation.confidence, confidence_basis=brief.what_would_settle_it,
    )
    assert res.success is True, res.error
    res_id = res.data["entity_id"]

    dec = manage_decision(
        "open", project, **_writer_kwargs(),
        question=brief.restated_plainly, owner="user:shubham", owner_type="user",
        options=[o.name for o in brief.options], related_research=[res_id],
    )
    assert dec.success is True, dec.error
    dec_id = dec.data["entity_id"]

    decided = manage_decision(
        "decide", project, **_writer_kwargs(), entity_id=dec_id,
        chosen_option=brief.recommendation.option, rationale=brief.recommendation.because,
    )
    assert decided.success is True, decided.error

    linked = manage_research("link_decision", project, **_writer_kwargs(agent_id="guidance"), entity_id=res_id, feeds_decision=dec_id)
    assert linked.success is True, linked.error

    entities = current_entities(project.events_path)
    assert entities[res_id].feeds_decision == dec_id

    why_text = render_why(dec_id, entities)
    assert "Team with roles" in why_text
    assert brief.recommendation.because in why_text
    assert brief.restated_plainly in why_text


def test_why_on_an_unknown_decision_says_so_plainly(tmp_path):
    project = _make_project(tmp_path)
    entities = current_entities(project.events_path)
    assert "No decision" in render_why("DEC-999", entities)


def test_ppa_why_renders_from_the_ledger(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = create_project("CLI Why Project", "seed requirement", _profile(), projects_root=tmp_path / "projects")

    dec = manage_decision("open", project, **_writer_kwargs(), question="Which hosting provider?", owner="user:shubham", owner_type="user")
    assert dec.success is True, dec.error
    dec_id = dec.data["entity_id"]
    decided = manage_decision("decide", project, **_writer_kwargs(), entity_id=dec_id, chosen_option="AWS", rationale="team already runs everything else there")
    assert decided.success is True, decided.error

    runner = CliRunner()
    result = runner.invoke(app, ["why", project.slug, dec_id])

    assert result.exit_code == 0, result.output
    assert "AWS" in result.output
    assert "team already runs everything else there" in result.output


# ---------------------------------------------------------------------------
# Done when: deferring produces a DECIDE_LATER and a safe-default ASM.
# ---------------------------------------------------------------------------


def test_deferring_produces_decide_later_and_a_linked_safe_default_assumption(tmp_path):
    project = _make_project(tmp_path)
    brief = parse_guidance_brief(_BRIEF_JSON)

    asm = manage_assumption(
        "create", project, **_writer_kwargs(),
        statement=brief.safe_default_if_deferred, reason=f"deferred Guidance recommendation: {brief.recommendation.because}",
        impact="MEDIUM", confidence=brief.recommendation.confidence, confidence_basis=brief.what_would_settle_it,
    )
    assert asm.success is True, asm.error
    asm_id = asm.data["entity_id"]

    dec = manage_decision(
        "open", project, **_writer_kwargs(),
        question=brief.restated_plainly, owner="user:shubham", owner_type="user",
        options=[o.name for o in brief.options], current_assumption=asm_id,
    )
    assert dec.success is True, dec.error
    dec_id = dec.data["entity_id"]

    deferred = manage_decision(
        "defer", project, **_writer_kwargs(), entity_id=dec_id,
        defer_reason="user wants to think about it more", owner="user:shubham", owner_type="user",
    )
    assert deferred.success is True, deferred.error

    entities = current_entities(project.events_path)
    assert entities[dec_id].status == "DECIDE_LATER"
    assert entities[dec_id].current_assumption == asm_id
    assert entities[asm_id].statement == brief.safe_default_if_deferred


# ---------------------------------------------------------------------------
# Done when: the subagent's context is isolated, and it alone can write
# RES-nnn.
# ---------------------------------------------------------------------------


def test_guidance_grant_is_isolated_and_exclusive_for_research():
    assert "manage_research" in GRANTS["guidance"]
    assert "manage_research" not in GRANTS["discovery"]
    # Guidance's own write surface never overlaps Discovery's — the only
    # thing they share is a read, never a write.
    guidance_writes = {t for t in GRANTS["guidance"] if not t.startswith("read_")}
    discovery_writes = {t for t in GRANTS["discovery"] if not t.startswith("read_")}
    assert not guidance_writes & discovery_writes


def test_guidance_server_exposes_only_its_own_grant(tmp_path):
    project = _make_project(tmp_path)
    _server, allowed = _guidance_server_and_allowed_tools(project)
    bare_names = {name.split("__")[-1] for name in allowed}
    assert bare_names == GRANTS["guidance"]
    assert all(name.startswith("mcp__guidance-tools__") for name in allowed)


def test_no_open_guidance_item_returns_ok_with_nothing_to_do(tmp_path):
    project = _make_project(tmp_path)
    result = run_guidance_session(project, actor_id="user:shubham", session_id="sess-guidance")
    assert result.status.value == "OK"
    assert "nothing queued" in result.summary


# ---------------------------------------------------------------------------
# One real Guidance session — steps 1-6 are the model's own job, proven
# live.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_a_real_guidance_session_produces_a_schema_valid_brief_and_persists_it(tmp_path):
    project = _make_project(tmp_path)
    unk = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="Who is the target user, really — do they manage their own invoices or a team's?",
        area="users", why_it_matters="user said they haven't thought about it at all",
        blocking=True, route="GUIDANCE", owner_type="agent",
    )
    assert unk.success is True, unk.error

    entities_before = current_entities(project.events_path)
    result = run_guidance_session(project, actor_id="user:shubham", session_id="sess-guidance-live")

    assert result.status.value == "OK", result.summary
    brief = GuidanceBrief.model_validate(result.data["brief"])
    assert len(brief.options) >= MIN_OPTIONS
    assert brief.recommendation.option

    entities_after = current_entities(project.events_path)
    new_research = [
        eid for eid in entities_after
        if eid not in entities_before and entity_type_for(eid) is EntityType.RESEARCH_FINDING
    ]
    assert new_research, "Guidance session did not persist a ResearchFinding"
