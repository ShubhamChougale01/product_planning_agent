"""Case 1 (S12.2) — correct tool selection: right tool, first try.

Marked `live_model` — this is the one claim in the whole suite that is
inherently about model judgment, not deterministic policy: which tools it
actually called, in which order, first try or not. Proven against one real
INTAKE turn (T24's own worked example, structurally one turn by design —
`ppa.agents.turn.run_discovery_turn`'s own docstring), reusing `ppa.agents.
modes.intake.evaluate_intake_shape` for the *content* claim and this case's
own audit-log read for the *tool-selection* claim.

**First live run, corrected in-flight**: the first attempt asserted zero
rejected calls of any category. A real turn made several `VALIDATION`
rejects on `manage_requirement` (missing `covers_areas`/provenance) before
supplying them correctly — that is case 4's own claim ("validation error,
corrected and retried"), not this one's. Selecting the *right* tool and
calling it with *correct arguments* are different claims; this case checks
only the former — no `PERMISSION` reject (the actual "wrong tool, not
granted" signal) ever appears, and every attempted tool stays within
INTAKE's own granted set. `VALIDATION`/`BUSINESS` rejects are recorded on
the outcome for visibility but do not fail this case.
"""

from __future__ import annotations

import pytest

from ppa.agents.discovery import DiscoveryAgent
from ppa.agents.modes.intake import evaluate_intake_shape
from ppa.ledger.audit import read_audit_records
from ppa.ledger.materialize import current_entities
from ppa.results.categories import ErrorCategory
from ppa.tools.dispatch import InvocationContext
from tests.eval.cases._helpers import make_project
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_01"
CASE_NAME = "correct tool selection, first try"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path, name="Vendor Invoice Tracker Case01")
    ctx = InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="eval-case-01", audit_path=project.audit_path,
    )

    result = DiscoveryAgent().invoke(ctx)

    entities = current_entities(project.events_path)
    shape = evaluate_intake_shape(entities, reply_text=result.summary)

    audit = read_audit_records(project.audit_path)
    rejects = [r for r in audit if r.operation == "reject"]
    wrong_tool_rejects = [r for r in rejects if r.result.category is ErrorCategory.PERMISSION]
    writes = [r for r in audit if r.operation == "write" and r.result.success]

    notes: list[str] = []
    passed = True
    if not shape.ok:
        passed = False
        notes.append(f"intake shape violated: {shape.violations}")
    if wrong_tool_rejects:
        passed = False
        notes.append(f"{len(wrong_tool_rejects)} PERMISSION reject(s) — a tool this agent isn't granted "
                      f"was attempted: {[(r.tool, r.result.code) for r in wrong_tool_rejects]}")
    if not writes:
        passed = False
        notes.append("no successful write tool call was recorded at all")
    if rejects and not wrong_tool_rejects:
        notes.append(f"(informational, not a failure) {len(rejects)} non-permission reject(s) on the "
                      f"right tool: {[(r.tool, r.result.code) for r in rejects]}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_selection_correct=passed,
        tool_calls_attempted=len(audit), tool_calls_invalid=len(wrong_tool_rejects),
    )


@pytest.mark.live_model
def test_correct_tool_selection_first_try(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
