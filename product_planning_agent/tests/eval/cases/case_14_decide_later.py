"""Case 14 (S12.2) — "decide later": DEC with dates, owner, current
assumption.

Marked `live_model`. `answer_kind="decide_later"` (`ppa.tools.interaction.
ask_user`'s own four answer kinds) is a distinct affordance from any of the
seven "I don't know" kinds `ppa.engines.dont_know_classifier` names — a
person saying "not now" rather than "I don't know." Nothing in `mode_
clarify.md` told a real turn how to react to one until this task added it
(see this case's own first live run, which found the gap) — this proves the
fix: a real CLARIFY turn, handed a question already answered `decide_later`,
opens a real `Decision` with `current_assumption` set, then defers it to
`DECIDE_LATER` with a computed `expected_decision_date` and a real owner.
"""

from __future__ import annotations

import pytest

from ppa.agents.discovery import DiscoveryAgent, DiscoveryMode
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.store import read_project_meta, write_project_meta
from ppa.tools.dispatch import InvocationContext
from ppa.tools.interaction import answer_pending_question, ask_user
from tests.eval.cases._helpers import make_project, writer_kwargs
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_14"
CASE_NAME = "decide later, DEC with dates/owner/current assumption"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path, name="Decide Later Case14")

    asked = ask_user(
        [{
            "text": "Which payment processor should we integrate with?",
            "why_asked": "determines integration scope and PCI posture",
        }],
        project, **writer_kwargs(),
    )
    question_id = asked.data[0]["question_id"]
    answer_pending_question(
        project, question_id, {"answer_kind": "decide_later"}, **writer_kwargs(),
    )

    meta = read_project_meta(project.events_path)
    meta["discovery_mode"] = DiscoveryMode.CLARIFY.value
    write_project_meta(project.events_path, meta)

    entities_before = current_entities(project.events_path)
    ctx = InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="eval-case-14", audit_path=project.audit_path,
    )
    DiscoveryAgent().invoke(ctx)
    entities_after = current_entities(project.events_path)

    new_or_changed_decisions = [
        eid for eid, e in entities_after.items()
        if entity_type_for(eid) is EntityType.DECISION and (eid not in entities_before or entities_before[eid] != e)
    ]

    notes: list[str] = []
    passed = True
    matching = [
        eid for eid in new_or_changed_decisions
        if entities_after[eid].status == "DECIDE_LATER"
        and entities_after[eid].expected_decision_date is not None
        and entities_after[eid].owner
        and entities_after[eid].current_assumption
    ]
    if not matching:
        passed = False
        found = {eid: entities_after[eid].model_dump() for eid in new_or_changed_decisions}
        notes.append(f"no DECIDE_LATER Decision with date+owner+current_assumption found; decisions seen: {found}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_selection_correct=passed,
    )


@pytest.mark.live_model
def test_decide_later_produces_a_tracked_decision(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
