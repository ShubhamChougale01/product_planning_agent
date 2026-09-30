"""Case 15 (S12.2) — requirement version change: new version, impact
report, gate recomputed.

Proven directly against the real writers (`ppa.tools.discovery_tools.
manage_requirement`), the real impact engine (`ppa.engines.impact.
analyze_impact`) and the real coverage engine (`ppa.engines.coverage.
compute_coverage`) — no model call: which requirement changed and why is
change handling's own qualitative job (`ppa.agents.modes.change`,
step 2 "adjudicate"), a different, live-model concern; this case proves
the three deterministic mechanics *given* a change already decided:
superseding writes a new version, the impact graph reaches what depended on
it, and coverage is derived fresh from current entities rather than cached
from before the change.
"""

from __future__ import annotations

from ppa.engines.coverage import compute_coverage
from ppa.engines.impact import analyze_impact
from ppa.ledger.materialize import current_entities
from ppa.tools.discovery_tools import manage_assumption, manage_requirement
from tests.eval.cases._helpers import make_project, writer_kwargs
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_15"
CASE_NAME = "requirement version change, impact and gate recomputed"

_AREA = "jobs"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path)
    notes: list[str] = []
    passed = True

    asm = manage_assumption(
        "create", project, **writer_kwargs(),
        statement="Assume a single-tenant deployment for v1", reason="not stated in the seed requirement",
        impact="LOW", confidence="LOW", confidence_basis="not stated",
    )
    asm_id = asm.data["entity_id"]

    req1 = manage_requirement(
        "create", project, **writer_kwargs(),
        statement="Users can create a vendor invoice record", type="functional",
        covers_areas=[_AREA], priority="must", confidence="MEDIUM", confidence_basis="implied by the seed requirement",
        depends_on_assumptions=[asm_id],
    )
    req1_id = req1.data["entity_id"]

    req2 = manage_requirement(
        "create", project, **writer_kwargs(),
        statement="Users can list their own vendor invoices", type="functional",
        covers_areas=["users"], priority="should", confidence="MEDIUM", confidence_basis="implied",
        depends_on_assumptions=[asm_id],
    )
    req2_id = req2.data["entity_id"]

    manage_requirement("confirm", project, **writer_kwargs(), entity_id=req1_id)

    coverage_before = compute_coverage(current_entities(project.events_path), project.profile)
    if coverage_before[_AREA].value != "SUFFICIENT":
        passed = False
        notes.append(f"expected {_AREA!r} SUFFICIENT once req1 is confirmed, got {coverage_before[_AREA].value!r}")

    superseded = manage_requirement(
        "supersede", project, **writer_kwargs(), entity_id=req1_id,
        change_reason="the vendor invoice statement needs a due-date field, a real scope change",
    )
    if not superseded.success:
        passed = False
        notes.append(f"supersede failed: {superseded.error}")

    entities_mid = current_entities(project.events_path)
    coverage_mid = compute_coverage(entities_mid, project.profile)
    if coverage_mid[_AREA].value == "SUFFICIENT":
        passed = False
        notes.append(f"{_AREA!r} still SUFFICIENT after superseding its only CONFIRMED requirement — gate is stale")

    impact = analyze_impact(req1_id, entities_mid)
    affected_ids = {a.entity_id for a in impact.affected}
    if req2_id not in affected_ids:
        passed = False
        notes.append(f"impact report from {req1_id} did not reach {req2_id} via the shared assumption {asm_id}")

    req3 = manage_requirement(
        "create", project, **writer_kwargs(),
        statement="Users can create a vendor invoice record with vendor, amount, due date and status",
        type="functional", covers_areas=[_AREA], priority="must",
        confidence="MEDIUM", confidence_basis="revised after scope change", depends_on_assumptions=[asm_id],
    )
    req3_id = req3.data["entity_id"]
    manage_requirement("confirm", project, **writer_kwargs(), entity_id=req3_id)

    coverage_after = compute_coverage(current_entities(project.events_path), project.profile)
    if coverage_after[_AREA].value != "SUFFICIENT":
        passed = False
        notes.append(f"expected {_AREA!r} SUFFICIENT again once the new version is confirmed, got {coverage_after[_AREA].value!r}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=5,
    )


def test_requirement_version_change_recomputes_impact_and_gate(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
