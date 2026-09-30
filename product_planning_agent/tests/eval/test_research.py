"""T29 eval — Research mode and provider degradation.

Degradation (UNAVAILABLE, FAILED-then-degrade, staleness, the readiness
gate exception) is fully mechanical and proven directly, no model
involved — the whole point of this task is that absence must degrade
*honestly*, which is exactly the part that must never depend on a real
model actually being reachable. Real, successful batched research is the
model's own job, proven live once in `test_a_real_research_session_
batches_the_queue_and_persists_findings` (marked `live_model`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ppa.agents.subagents.research import (
    _open_research_unknowns,
    is_stale,
    run_research_session,
    stale_findings_underpinning_open_decisions,
)
from ppa.config.profiles import UserProfile
from ppa.engines.open_items import collect_open_items
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import create_project
from ppa.providers.research import NullResearchProvider, empty_result, failed_result, unavailable_result
from ppa.tools.discovery_tools import manage_decision, manage_research, manage_unknown

NOW = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Research Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-research", now=NOW)
    base.update(overrides)
    return base


def _seed_research_unknown(project, *, question="Which database scales better here?", blocking=False):
    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question=question, area="platform", why_it_matters="shapes the data layer architecture",
        blocking=blocking, route="RESEARCH", owner_type="agent",
    )
    assert result.success is True, result.error
    return result.data["entity_id"]


# ---------------------------------------------------------------------------
# Done when: with research disabled, a session still reaches READY.
# ---------------------------------------------------------------------------


def test_a_non_blocking_research_item_never_blocks_readiness(tmp_path):
    project = _make_project(tmp_path)
    _seed_research_unknown(project, blocking=False)

    entities = current_entities(project.events_path)
    _ready, blockers = check_readiness(entities, _profile())
    assert not [b for b in blockers if b.condition == "blocking_unknown"]


def test_a_blocking_research_item_does_block_readiness(tmp_path):
    """The one exception the task's own gate rule states explicitly:
    blocking is what gates, never route — a blocking RESEARCH item still
    blocks, same as any other blocking Unknown."""

    project = _make_project(tmp_path)
    _seed_research_unknown(project, blocking=True)

    entities = current_entities(project.events_path)
    _ready, blockers = check_readiness(entities, _profile())
    assert [b for b in blockers if b.condition == "blocking_unknown"]


# ---------------------------------------------------------------------------
# Done when: every unresearched item appears in open items with an honest
# explanation; degraded=True on reduced-capability success; the agent never
# fabricates a researched answer.
# ---------------------------------------------------------------------------


def test_unavailable_provider_degrades_every_queued_item_honestly(tmp_path):
    project = _make_project(tmp_path)
    unk_id = _seed_research_unknown(project, question="Which auth model shapes our scope here?")

    entities_before = current_entities(project.events_path)
    result = run_research_session(project, actor_id="user:shubham", session_id="sess-research", provider=NullResearchProvider())

    assert result.data["degraded"] is True
    assert result.data["outcome"] == "UNAVAILABLE"
    assert "can't research this here" in result.summary

    entities_after = current_entities(project.events_path)
    # Never fabricates a researched answer: no ResearchFinding was created.
    new_findings = [eid for eid in entities_after if eid not in entities_before and entity_type_for(eid) is EntityType.RESEARCH_FINDING]
    assert not new_findings

    open_items = collect_open_items(entities_after)
    item = next(i for i in open_items if i.entity_id == unk_id)
    assert item.kind == "research_queued"

    unknown = entities_after[unk_id]
    assert unknown.owner_type == "user"
    assert unknown.status == "OPEN"
    assert unknown.route == "RESEARCH"
    assert "can't research this here" in unknown.why_it_matters


def test_failed_search_and_unavailable_produce_different_messages(monkeypatch, tmp_path):
    project = _make_project(tmp_path)
    _seed_research_unknown(project)

    import ppa.agents.subagents.research as research_module

    def _always_raises(project, queue):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(research_module, "_run_batched_research_turn", _always_raises)

    result = run_research_session(project, actor_id="user:shubham", session_id="sess-research")

    assert result.data["degraded"] is True
    assert result.data["outcome"] == "FAILED"
    assert "search failed" in result.summary
    assert "can't research this here" not in result.summary  # the UNAVAILABLE-only phrasing


def test_unavailable_and_failed_messages_are_textually_distinct():
    unavailable = unavailable_result(degraded_answer="a guess")
    failed = failed_result(detail="timeout", degraded_answer="a guess")
    assert unavailable.message != failed.message
    assert "search failed" in failed.message
    assert "search failed" not in unavailable.message


# ---------------------------------------------------------------------------
# Done when: findings older than 90 days are flagged STALE when they
# underpin an open decision.
# ---------------------------------------------------------------------------


def test_stale_finding_underpinning_an_open_decision_is_flagged(tmp_path):
    project = _make_project(tmp_path)
    old_now = NOW - timedelta(days=100)

    res = manage_research(
        "create", project, **_writer_kwargs(agent_id="research", now=old_now),
        question="Which database scales better here?", method="web search",
        summary="Postgres handled this comfortably in two independent benchmarks.",
        options_found=["Postgres", "MongoDB"], confidence="MEDIUM", confidence_basis="two benchmarks agreed",
    )
    assert res.success is True, res.error
    res_id = res.data["entity_id"]

    dec = manage_decision("open", project, **_writer_kwargs(), question="Which database?", owner="agent:research", owner_type="agent")
    assert dec.success is True, dec.error
    dec_id = dec.data["entity_id"]

    linked = manage_research("link_decision", project, **_writer_kwargs(agent_id="research"), entity_id=res_id, feeds_decision=dec_id)
    assert linked.success is True, linked.error

    entities = current_entities(project.events_path)
    assert is_stale(entities[res_id], now=NOW)
    assert res_id in stale_findings_underpinning_open_decisions(entities, now=NOW)


def test_stale_finding_behind_a_decided_decision_is_not_flagged(tmp_path):
    project = _make_project(tmp_path)
    old_now = NOW - timedelta(days=100)

    res = manage_research(
        "create", project, **_writer_kwargs(agent_id="research", now=old_now),
        question="Which database scales better here?", method="web search",
        summary="Postgres handled this comfortably.", confidence="MEDIUM", confidence_basis="one benchmark",
    )
    res_id = res.data["entity_id"]
    dec = manage_decision("open", project, **_writer_kwargs(), question="Which database?", owner="agent:research", owner_type="agent")
    dec_id = dec.data["entity_id"]
    manage_research("link_decision", project, **_writer_kwargs(agent_id="research"), entity_id=res_id, feeds_decision=dec_id)
    decided = manage_decision("decide", project, **_writer_kwargs(), entity_id=dec_id, chosen_option="Postgres", rationale="benchmarks agree")
    assert decided.success is True, decided.error

    entities = current_entities(project.events_path)
    assert res_id not in stale_findings_underpinning_open_decisions(entities, now=NOW)


def test_a_fresh_finding_is_never_flagged_stale(tmp_path):
    project = _make_project(tmp_path)
    res = manage_research(
        "create", project, **_writer_kwargs(agent_id="research", now=NOW),
        question="Which database scales better here?", method="web search",
        summary="Postgres.", confidence="MEDIUM", confidence_basis="one benchmark",
    )
    entities = current_entities(project.events_path)
    assert not is_stale(entities[res.data["entity_id"]], now=NOW)


# ---------------------------------------------------------------------------
# Done when: empty research results return success, not an error, and are
# never retried.
# ---------------------------------------------------------------------------


def test_empty_result_is_a_success_not_an_error():
    result = empty_result(question="What's the airspeed velocity of an unladen swallow, for this product?")
    assert result.outcome == "AVAILABLE"
    assert result.degraded is False
    assert "nothing conclusive" in result.message


# ---------------------------------------------------------------------------
# Structural: nothing queued is a no-op OK, not an error.
# ---------------------------------------------------------------------------


def test_no_open_research_item_returns_ok_with_nothing_to_do(tmp_path):
    project = _make_project(tmp_path)
    result = run_research_session(project, actor_id="user:shubham", session_id="sess-research")
    assert result.status.value == "OK"
    assert "nothing queued" in result.summary


def test_open_research_unknowns_ignores_other_routes_and_closed_items(tmp_path):
    project = _make_project(tmp_path)
    research_id = _seed_research_unknown(project)
    manage_unknown(
        "record", project, **_writer_kwargs(),
        question="Who is the target user?", area="users", why_it_matters="needs guidance",
        blocking=True, route="GUIDANCE", owner_type="agent",
    )
    resolved_id = _seed_research_unknown(project, question="Some already-handled question")
    manage_unknown("resolve", project, **_writer_kwargs(), entity_id=resolved_id)

    entities = current_entities(project.events_path)
    queue_ids = {eid for eid, _ in _open_research_unknowns(entities)}
    assert queue_ids == {research_id}


# ---------------------------------------------------------------------------
# One real batched Research turn — real research is the model's own job,
# proven live.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_a_real_research_session_batches_the_queue_and_persists_findings(tmp_path):
    project = _make_project(tmp_path)
    _seed_research_unknown(project, question="Is PostgreSQL or MongoDB generally recommended for a transactional invoice-tracking system with relational data?")

    entities_before = current_entities(project.events_path)
    result = run_research_session(project, actor_id="user:shubham", session_id="sess-research-live")

    assert result.status.value == "OK", result.summary
    assert result.data["outcome"] == "AVAILABLE"
    assert result.data["degraded"] is False

    entities_after = current_entities(project.events_path)
    new_findings = [
        eid for eid in entities_after
        if eid not in entities_before and entity_type_for(eid) is EntityType.RESEARCH_FINDING
    ]
    assert new_findings, "Research session did not persist a ResearchFinding"
