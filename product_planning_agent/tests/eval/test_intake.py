"""T24 eval — one real Intake turn on the design's own example seed,
checked against every Done-when box in `tasks/t24_intake_mode.md`.

Marked `live_model` (decision #31, `blockers.md`) — excluded from the
default `pytest` run, same as T23's own real-turn test. Run explicitly with
`pytest -m live_model` or by naming it directly.
"""

from __future__ import annotations

import pytest

from ppa.agents.discovery import DiscoveryAgent
from ppa.agents.modes.intake import evaluate_intake_shape
from ppa.config.profiles import UserProfile
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.ledger.store import read_project_meta
from ppa.tools.dispatch import InvocationContext


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _ctx(project) -> InvocationContext:
    return InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="eval-intake", audit_path=project.audit_path,
    )


@pytest.mark.live_model
def test_intake_on_the_design_docs_own_vendor_invoice_example_meets_the_shape(tmp_path):
    """DESIGN.md S7.4's own worked example: "a tool for tracking vendor
    invoices." >= 3 proposed requirements, >= 2 confirmation-flagged
    assumptions, exactly one pending question, no silent assumptions, and a
    reply that reads like an understanding, not a wall of text."""

    project = create_project(
        "Vendor Invoice Tracker",
        "a tool for tracking vendor invoices",
        _profile(),
        projects_root=tmp_path / "projects",
    )

    result = DiscoveryAgent().invoke(_ctx(project))

    entities = current_entities(project.events_path)
    report = evaluate_intake_shape(entities, reply_text=result.summary)

    assert report.ok, report.violations

    # Coverage moves as a *consequence* of what was written — never
    # declared. There is no tool anywhere in the registry that could set it
    # directly; this is a structural guarantee, asserted here so a future
    # tool addition can't quietly reintroduce one.
    from ppa.agents.registry import GRANTS

    assert not any(name.startswith("set_coverage") or name.startswith("declare_coverage") for name in GRANTS["discovery"])

    # Intake is structurally one turn — it must have handed off to CLARIFY.
    assert read_project_meta(project.events_path)["discovery_mode"] == "CLARIFY"
