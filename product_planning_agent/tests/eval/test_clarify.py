"""T25 eval — one real Clarify round on a post-intake ledger, checked
against every per-round Done-when box in
`tasks/t25_clarify_mode_question_engine.md`.

Marked `live_model` (decision #31, `blockers.md`) — excluded from the
default `pytest` run. Run explicitly with `pytest -m live_model` or by
naming it directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.agents.discovery import DiscoveryAgent, DiscoveryMode
from ppa.agents.modes.clarify import evaluate_clarify_round
from ppa.config.profiles import UserProfile
from ppa.ledger.events import EventType
from ppa.ledger.materialize import current_entities
from ppa.ledger.models import Assumption, Requirement
from ppa.ledger.project import create_project
from ppa.ledger.store import append_event, read_project_meta, write_project_meta
from ppa.tools.dispatch import InvocationContext

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _ctx(project) -> InvocationContext:
    return InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="eval-clarify", audit_path=project.audit_path,
    )


def _seed_post_intake_state(project) -> None:
    """A small, plausible post-INTAKE ledger — a couple of requirements and
    an assumption already recorded, mirroring what T24's own intake turn
    produces, so CLARIFY has real remaining gaps to choose among rather
    than a completely empty ledger."""

    req = Requirement(
        id="REQ-001", created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="MEDIUM", confidence_basis="implied by the seed requirement", status="PROPOSED",
        statement="Users can create a vendor invoice record with vendor, amount and due date",
        type="functional", covers_areas=["jobs"], priority="must",
    )
    append_event(
        dict(
            ts=NOW, type=EventType.REQUIREMENT_CREATED, entity_id="REQ-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=None,
            source="fixture", reason="seed post-intake state", before=None,
            after=req.model_dump(mode="json"), session_id="eval-clarify",
        ),
        project.events_path,
    )
    asm = Assumption(
        id="ASM-001", created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="LOW", confidence_basis="not stated", status="PROPOSED",
        statement="Single-company, web-only tool for v1", reason="not stated in the seed requirement",
        impact="MEDIUM", user_confirmation_required=True,
    )
    append_event(
        dict(
            ts=NOW, type=EventType.ASSUMPTION_CREATED, entity_id="ASM-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=None,
            source="fixture", reason="seed post-intake state", before=None,
            after=asm.model_dump(mode="json"), session_id="eval-clarify",
        ),
        project.events_path,
    )
    meta = read_project_meta(project.events_path)
    meta["discovery_mode"] = DiscoveryMode.CLARIFY.value
    write_project_meta(project.events_path, meta)


@pytest.mark.live_model
def test_clarify_round_on_a_post_intake_ledger_meets_the_per_round_shape(tmp_path):
    project = create_project(
        "Vendor Invoice Tracker", "a tool for tracking vendor invoices", _profile(), projects_root=tmp_path / "projects",
    )
    _seed_post_intake_state(project)

    entities_before = current_entities(project.events_path)
    DiscoveryAgent().invoke(_ctx(project))
    entities_after = current_entities(project.events_path)

    report = evaluate_clarify_round(entities_before, entities_after)
    assert report.ok, report.violations
