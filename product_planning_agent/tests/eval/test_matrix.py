"""T33 eval — the real, multi-round proofs `tasks/t33_eval_fixtures_and_
personas.md`'s own Done-when boxes require. Marked `live_model` throughout
(decision #31, `blockers.md`) — excluded from the default `pytest` run.
Run explicitly with `pytest -m live_model tests/eval/test_matrix.py`.

Each test drives `tests.eval.harness.run_session` — a real, multi-round
Discovery session against a `(fixture, persona)` pair. See `harness.py`'s
own module docstring for the full mechanism.
"""

from __future__ import annotations

import pytest

from ppa.agents.modes.intake import evaluate_intake_shape
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from tests.eval.harness import load_fixture, load_fixtures, run_session
from tests.eval.personas import PERSONAS

_COMPLETION_FIXTURE = "f06_detailed_k8s_audit_alerting"
_DEFAULT_MAX_ROUNDS = 4
_MAX_ROUNDS_BY_PERSONA = {
    "contradicts_self": 5,  # needs to actually reach round 4
    "defers_to_client": 5,  # give T27 routing more than one chance to land
}


# ---------------------------------------------------------------------------
# Done when: six personas, each able to complete a session unattended.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
@pytest.mark.parametrize("persona_name", sorted(PERSONAS))
def test_every_persona_completes_a_session_unattended(persona_name, tmp_path):
    fixture = load_fixture(_COMPLETION_FIXTURE)
    max_rounds = _MAX_ROUNDS_BY_PERSONA.get(persona_name, _DEFAULT_MAX_ROUNDS)

    report = run_session(
        fixture, PERSONAS[persona_name], projects_root=tmp_path / "projects", max_rounds=max_rounds,
    )

    assert report.completed, report.break_reason
    assert len(report.rounds) >= 1

    if persona_name == "impatient":
        # "Just build it" must never talk the gate into READY.
        assert report.ready is False


@pytest.mark.live_model
def test_defers_to_client_routes_at_least_one_item_externally(tmp_path):
    """T27's own signature: an `Unknown` with `owner_type == "external"`
    (and, once T26's own three-call sequence lands, a linked provisional
    `Assumption`) — the client questionnaire's own raw material.

    Deliberately uses a *client-project* fixture, not `_COMPLETION_
    FIXTURE` — a live run against `f06` (a purely internal Kubernetes
    tool, no client anywhere in its own seed requirement) produced zero
    externally-owned `Unknown`s, which on inspection is the *correct*
    behavior: nothing in that project's own context ever named a client
    for "defers_to_client"'s answers to plausibly defer to. `needs_
    external_input` routing is a function of context, not of the answer's
    own wording alone — this fixture actually establishes a client, so the
    persona's deferrals have somewhere real to route to."""

    fixture = load_fixture("f03_vague_legacy_invoicing_client")
    report = run_session(
        fixture, PERSONAS["defers_to_client"], projects_root=tmp_path / "projects", max_rounds=5,
    )
    assert report.completed, report.break_reason

    entities = current_entities(report.project.events_path)
    external_unknowns = [
        e for eid, e in entities.items()
        if entity_type_for(eid) is EntityType.UNKNOWN and e.owner_type == "external"
    ]
    assert external_unknowns, (
        "expected at least one externally-owned Unknown after a full session of "
        "\"that's the client's call\" answers — none were produced"
    )


# ---------------------------------------------------------------------------
# Done when: at least two fixtures break the agent on first run.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_at_least_two_fixtures_break_the_agent_on_first_run(tmp_path):
    """One real INTAKE round per fixture, the straightforward persona —
    this task's own "if none do, they are too easy to be useful" bar,
    checked directly rather than assumed from the `adversarial` flag
    fixtures declare on themselves. "Broke" here means either the harness's
    own hard failure (a crash, an escalation) *or* a real INTAKE turn that
    fails T24's own shape check (`evaluate_intake_shape`) — >= 3 proposed
    requirements, >= 2 confirmation-flagged assumptions, exactly one
    pending question, no silent assumptions — the honest bar T24 already
    established for what a *correct* Intake turn produces, not merely a
    non-crashing one."""

    broke: list[tuple[str, str]] = []
    for fixture in load_fixtures():
        report = run_session(
            fixture, PERSONAS["knows_their_stuff"], projects_root=tmp_path / "projects", max_rounds=1,
        )
        if report.broke:
            broke.append((fixture.name, report.break_reason or "unknown"))
            continue

        entities = current_entities(report.project.events_path)
        reply_text = report.rounds[-1].agent_summary if report.rounds else ""
        shape = evaluate_intake_shape(entities, reply_text=reply_text)
        if not shape.ok:
            broke.append((fixture.name, f"failed evaluate_intake_shape: {shape.violations}"))

    assert len(broke) >= 2, f"expected at least two fixtures to break the agent on first run; got: {broke}"
