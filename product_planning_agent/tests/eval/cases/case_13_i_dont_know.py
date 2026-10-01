"""Case 13 (S12.2) — "I don't know": classified, routed, no loop.

Marked `live_model`. Complements the broader T26 live proof (`tests/eval/
test_dont_know.py::test_a_real_clarify_turn_classifies_and_routes_all_seven_
kinds`, which hands the model all seven `SIGNAL_EXAMPLES` verbatim at
once) with a narrower, distinct claim: given one raw, unprompted "I don't
know"-shaped reply — genuinely unexplored, not told which of the seven
kinds it is — a real turn (a) still classifies and routes it correctly, and
(b) does not loop: no second, near-duplicate question about the same gap is
asked instead of routing. "No loop" is checked structurally
(`ppa.engines.dont_know_classifier.is_same_question` against every new
question this turn asked), not by trusting the model's own narration.
"""

from __future__ import annotations

import pytest

from ppa.agents.discovery import DiscoveryAgent, DiscoveryMode
from ppa.agents.modes.dont_know import evaluate_dont_know_routing
from ppa.engines.dont_know_classifier import SIGNAL_EXAMPLES, is_same_question
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.store import read_project_meta, write_project_meta
from ppa.tools.dispatch import InvocationContext
from ppa.tools.interaction import answer_pending_question, ask_user
from tests.eval.cases._helpers import make_project, writer_kwargs
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_13"
CASE_NAME = "\"I don't know\", classified, routed, no loop"

_ORIGINAL_QUESTION = "Who is the target user, exactly?"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path, name="I Dont Know Case13")

    asked = ask_user(
        [{"text": _ORIGINAL_QUESTION, "why_asked": "scoping who this is for"}],
        project, **writer_kwargs(),
    )
    question_id = asked.data[0]["question_id"]
    answer_pending_question(
        project, question_id,
        {"answer_kind": "dont_know", "answer_text": SIGNAL_EXAMPLES["unexplored"]},
        **writer_kwargs(),
    )

    meta = read_project_meta(project.events_path)
    meta["discovery_mode"] = DiscoveryMode.CLARIFY.value
    write_project_meta(project.events_path, meta)

    entities_before = current_entities(project.events_path)
    ctx = InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="eval-case-13", audit_path=project.audit_path,
    )
    DiscoveryAgent().invoke(ctx)
    entities_after = current_entities(project.events_path)

    report = evaluate_dont_know_routing("unexplored", entities_before, entities_after)

    new_questions = [
        e for eid, e in entities_after.items()
        if eid not in entities_before and entity_type_for(eid) is EntityType.QUESTION_ANSWER
    ]
    looped = any(is_same_question(q.text, _ORIGINAL_QUESTION) for q in new_questions)

    notes: list[str] = []
    passed = True
    if not report.ok:
        passed = False
        notes.append(f"routing violations: {report.violations}")
    if looped:
        passed = False
        notes.append(f"the original question ({_ORIGINAL_QUESTION!r}) was re-asked verbatim — a loop")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_selection_correct=passed,
    )


@pytest.mark.live_model
def test_i_dont_know_is_classified_routed_and_never_loops(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
