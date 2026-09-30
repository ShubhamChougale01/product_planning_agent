"""T34 — closing blockers.md decisions #33 (T25) and #34 (T26): three
session-level CLARIFY Done-when boxes and the `always_idk` anti-loop guard,
each provable only across a *real, multi-round* session, never a single
round (that is exactly what decisions #33/#34 themselves say is missing).

Marked `live_model`. Drives its own round loop rather than reusing `tests.
eval.harness.run_session` directly — that function is already a tested T33
artifact whose own public shape (`SessionReport`) does not carry a
per-round entity diff, and this test needs exactly that (via `ppa.agents.
modes.clarify.evaluate_clarify_round`) to check what a specific round did,
not just whether the session as a whole survived. The loop below is
otherwise the same shape: invoke, find `PENDING` questions, answer via the
persona, repeat.

One session, `always_idk` against `f06_detailed_k8s_audit_alerting` (T33's
own choice for this persona — the most technical fixture in the set, the
best chance of `factually_unknown`/RESEARCH routing showing up
organically), closes all three at once:

- **Decision #33, box 1** — "research routed at least once per session":
  `unknowns_routed_to_research_count` summed across every round.
- **Decision #33, box 2** — "round 4 triggers the assumptions offer":
  once `round_number >= 4` and the gate has not passed, that round records
  at least one real Assumption rather than only asking.
- **Decision #33, box 3** — "three consecutive `dont_know` triggers
  assumption-heavy mode": `always_idk` never answers anything else, so this
  session is assumption-heavy-triggering from round 1 onward by
  construction — checked as a whole-session ratio (assumptions recorded
  are not dwarfed by questions asked) rather than pinned to one exact
  round boundary, since with this persona the fatigue threshold is crossed
  almost immediately and stays crossed.
- **Decision #34** — the anti-loop guard's forced escalation actually
  firing, not just the session surviving: at least one blocking
  `Unknown(route="GUIDANCE")` by the end, and no question ever repeated
  verbatim (`ppa.engines.dont_know_classifier.is_same_question`).
"""

from __future__ import annotations

import uuid

import pytest

from ppa.agents.base import AgentResultStatus
from ppa.agents.discovery import DiscoveryAgent
from ppa.agents.modes.clarify import evaluate_clarify_round
from ppa.engines.dont_know_classifier import is_same_question
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import create_project
from ppa.tools.dispatch import InvocationContext
from ppa.tools.interaction import answer_pending_question
from tests.eval.harness import _ctx, _pending_questions, load_fixture
from tests.eval.personas import PERSONAS

MAX_ROUNDS = 6
FIXTURE_NAME = "f06_detailed_k8s_audit_alerting"
PERSONA_NAME = "always_idk"


@pytest.mark.live_model
def test_always_idk_multiround_session_closes_decisions_33_and_34(tmp_path):
    fixture = load_fixture(FIXTURE_NAME)
    persona = PERSONAS[PERSONA_NAME]()

    project = create_project(
        f"{FIXTURE_NAME}-{PERSONA_NAME}-{uuid.uuid4().hex[:6]}",
        fixture.seed_requirement, fixture.profile, projects_root=tmp_path / "projects",
    )

    research_routed_total = 0
    assumptions_total = 0
    questions_total = 0
    round4_plus_assumption_offer_seen = False
    all_question_texts: list[str] = []
    broke = False
    break_reason = ""

    for round_number in range(1, MAX_ROUNDS + 1):
        entities_before = current_entities(project.events_path)
        ctx = _ctx(project)
        result = DiscoveryAgent().invoke(ctx)

        if result.status in (AgentResultStatus.NON_RECOVERABLE, AgentResultStatus.RECOVERABLE):
            broke = True
            break_reason = f"round {round_number}: agent reported {result.status.value}: {result.summary}"
            break

        entities_after = current_entities(project.events_path)
        round_report = evaluate_clarify_round(entities_before, entities_after)
        research_routed_total += round_report.unknowns_routed_to_research_count
        assumptions_total += round_report.assumptions_recorded_count
        questions_total += round_report.questions_asked_count

        new_questions = [
            e for eid, e in entities_after.items()
            if eid not in entities_before and entity_type_for(eid) is EntityType.QUESTION_ANSWER
        ]
        all_question_texts.extend(q.text for q in new_questions)

        ready_here, _blockers = check_readiness(entities_after, fixture.profile)
        if round_number >= 4 and not ready_here and round_report.assumptions_recorded_count > 0:
            round4_plus_assumption_offer_seen = True

        pending = _pending_questions(project)
        if not pending:
            break

        for question in pending:
            answer = persona.answer(question.model_dump(mode="json"), round_number=round_number)
            answer_result = answer_pending_question(
                project, question.id, answer,
                actor_id=f"persona:{persona.name}", session_id=ctx.session_id, workflow_state="DISCOVERY",
            )
            if not answer_result.success:
                broke = True
                break_reason = f"round {round_number}: recording answer to {question.id} failed: {answer_result.error}"
                break
        if broke:
            break

    final_entities = current_entities(project.events_path)
    guidance_unknowns = [
        e for eid, e in final_entities.items()
        if entity_type_for(eid) is EntityType.UNKNOWN and e.route == "GUIDANCE" and e.blocking
    ]
    no_repeats = all(
        not is_same_question(a, b)
        for i, a in enumerate(all_question_texts)
        for b in all_question_texts[i + 1:]
    )

    violations: list[str] = []
    if broke:
        violations.append(f"session broke: {break_reason}")
    if research_routed_total < 1:
        violations.append(
            f"decision #33 box 1: zero Unknown(route=RESEARCH) across {len(all_question_texts)} question(s) "
            f"over the whole session — research was never routed to"
        )
    if not round4_plus_assumption_offer_seen:
        violations.append(
            "decision #33 box 2: no round from 4 onward (while not ready) recorded a real assumption — "
            "the round-4 assumptions offer never fired"
        )
    if questions_total > 0 and assumptions_total < questions_total:
        violations.append(
            f"decision #33 box 3: {assumptions_total} assumption(s) recorded against {questions_total} "
            f"question(s) asked — always_idk should trigger assumption-heavy mode from very early on, "
            f"not merely keep pace with questions"
        )
    if not guidance_unknowns:
        violations.append("decision #34: no blocking Unknown(route=GUIDANCE) — the anti-loop guard never forced escalation")
    if not no_repeats:
        violations.append("decision #34: the same question text was asked more than once verbatim — a real loop")

    assert not violations, violations
