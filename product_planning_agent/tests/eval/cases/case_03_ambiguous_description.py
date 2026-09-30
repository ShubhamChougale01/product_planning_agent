"""Case 3 (S12.2) — ambiguous description: disambiguated by
`do_not_use_when`.

Marked `live_model`. `ask_user`'s own `ToolSpec.do_not_use_when`
(`ppa/tools/interaction.py`) names the ambiguity directly: "the agent could
resolve this itself with a documented assumption — use manage_assumption
instead." `manage_assumption` and `ask_user` are the two tools a
superficial reading could confuse for the same job ("find out the rollout
plan") — this case proves a real turn resolves that ambiguity the way the
spec says to, for a gap that is genuinely, cleanly assumable: `rollout` is
non-critical for an `engineer` profile (`ppa.config.profiles.
critical_areas`) and LOW-impact (`ppa.config.autonomy.
may_assume_silently`), so the documented rule is "assume, don't ask."

**Corrected in-flight, twice.** First live run: letting one autonomous
CLARIFY round pick its own gaps organically left `rollout` uncontested
against several still-completely-untouched *critical* areas (this fixture
seeded only one requirement), which a real turn reasonably prioritized
instead — never reaching `rollout` at all. Fixed by asking directly, the
same "hand the model a direct instruction" shape `tests/eval/
test_dont_know.py`'s own live test already uses.

Second live run, asked directly: the real turn did *not* pick
`manage_assumption` — it picked a third tool this case's own first draft
didn't account for, `manage_unknown(route="OPTIONAL")`, with a genuinely
well-reasoned rejection of `ask_user` (own `do_not_use_when`), `manage_
assumption` ("I have zero signal to build a confident assumption from,
silently assuming would violate 'no silent assumptions without real
confidence'") and `manage_decision`, in favor of `manage_unknown`'s own
`use_when`: "the agent has identified something not yet known and needs to
record it with a resolution route." That is a *more* careful application
of exactly the `do_not_use_when`-driven disambiguation this case exists to
prove, not a miss — the original premise ("rollout is cleanly assumable
for an engineer") turned out to conflate "non-critical" with "silently
assumable," which `ppa.config.profiles`'s own §6.1 table (`jobs`,
`success`, `rollout` all "needs guidance" for an engineer, not "direct")
contradicts. The case accepts either a real `Assumption` or a real
`Unknown` naming the area — what it still must never accept is a wasted
question slot (an area this genuinely non-blocking never needed `ask_user`
for) or the gap going unrecorded. Whether the model also marks that
`Unknown` `blocking` is a separate judgment call this case does not police
— it varied between two live runs of this exact scenario and is arguably
defensible either way (§6.2's "no silent assumptions" instinct cuts toward
caution); that variance belongs to decision-quality tuning, not to "which
tool did it pick," which is this case's own actual claim.
"""

from __future__ import annotations

import functools

import anyio
import pytest

from ppa.agents.discovery import DiscoveryMode, render_system_prompt
from ppa.agents.turn import _mode_scoped_server_and_allowed_tools, _run_one_sdk_turn, _tool_discovery_hint
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType, Unknown
from ppa.ledger.store import read_project_meta, write_project_meta
from tests.eval.cases._helpers import NOW, make_project
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_03"
CASE_NAME = "ambiguous description, disambiguated by do_not_use_when"

_TARGET_AREA = "rollout"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path, name="Rollout Ambiguity Case03")

    meta = read_project_meta(project.events_path)
    meta["discovery_mode"] = DiscoveryMode.CLARIFY.value
    write_project_meta(project.events_path, meta)

    entities_before = current_entities(project.events_path)

    server, allowed_tools = _mode_scoped_server_and_allowed_tools(DiscoveryMode.CLARIFY, project)
    system_prompt = _tool_discovery_hint(allowed_tools) + "\n\n" + render_system_prompt(
        DiscoveryMode.CLARIFY, project.profile, today=NOW.date(),
    )
    user_message = (
        "One open gap this project has not addressed yet: how this should be rolled out to users "
        "(the `rollout` coverage area) — nothing has been said about it either way. Decide right now, "
        "using your own tool documentation (read each candidate tool's own `do_not_use_when` field if "
        "you are unsure) which single tool is the right one to close this specific gap, and call it. "
        "Do not ask a clarifying question about which tool to use — decide and act."
    )

    text, _cost = anyio.run(
        functools.partial(
            _run_one_sdk_turn, system_prompt=system_prompt, server=server, allowed_tools=allowed_tools,
            user_message=user_message,
        )
    )

    entities_after = current_entities(project.events_path)
    new_questions = [
        e for eid, e in entities_after.items()
        if eid not in entities_before and entity_type_for(eid) is EntityType.QUESTION_ANSWER
    ]
    new_assumptions = [
        e for eid, e in entities_after.items()
        if eid not in entities_before and entity_type_for(eid) is EntityType.ASSUMPTION
    ]
    new_unknowns: list[Unknown] = [
        e for eid, e in entities_after.items()
        if eid not in entities_before and entity_type_for(eid) is EntityType.UNKNOWN
    ]

    asked_about_rollout = any(_TARGET_AREA in q.target_areas for q in new_questions)
    assumed_rollout = any(_TARGET_AREA in a.affects_areas for a in new_assumptions)
    recorded_as_unknown = [u for u in new_unknowns if u.area == _TARGET_AREA]

    notes: list[str] = []
    passed = True
    if asked_about_rollout:
        passed = False
        notes.append(f"asked a question about {_TARGET_AREA!r} via ask_user — a non-blocking, non-critical "
                      "gap should never spend a question slot per ask_user's own do_not_use_when")
    if not assumed_rollout and not recorded_as_unknown:
        passed = False
        notes.append(f"neither an Assumption nor an Unknown was recorded for {_TARGET_AREA!r} — the gap "
                      f"was silently dropped; model's own text: {text!r}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_selection_correct=passed,
        tool_calls_attempted=len(new_questions) + len(new_assumptions) + len(new_unknowns),
    )


@pytest.mark.live_model
def test_ambiguous_description_disambiguated_by_do_not_use_when(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
