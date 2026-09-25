"""Impact graph tests (T11). Every Done-when box in
tasks/t11_impact_graph_and_conflicts.md that concerns the impact graph maps
to at least one test here.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from ppa.engines.impact import analyze_impact
from ppa.ledger.models import Assumption, Decision, Requirement

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _requirement(entity_id: str, **overrides) -> Requirement:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        confidence="HIGH",
        confidence_basis="user said it directly",
        statement=f"statement for {entity_id}",
        type="functional",
        priority="must",
    )
    base.update(overrides)
    return Requirement(**base)


def _assumption(entity_id: str, **overrides) -> Assumption:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        confidence="MEDIUM",
        confidence_basis="strongly implied",
        statement=f"assumption for {entity_id}",
        reason="inferred",
        impact="MEDIUM",
    )
    base.update(overrides)
    return Assumption(**base)


def _decision(entity_id: str, **overrides) -> Decision:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        question=f"question for {entity_id}",
        owner="user:shubham",
        owner_type="user",
        identified_at=NOW,
    )
    base.update(overrides)
    return Decision(**base)


# ---------------------------------------------------------------------------
# Done when: on a REQ-001 -> ASM-002 -> DEC-003 fixture, changing REQ-001
# returns both, with paths, in under 50ms.
# ---------------------------------------------------------------------------


def test_req_asm_dec_fixture_returns_both_with_paths_under_50ms():
    entities = {
        "REQ-001": _requirement("REQ-001", depends_on_assumptions=["ASM-002"], depends_on_decisions=["DEC-003"]),
        "ASM-002": _assumption("ASM-002"),
        "DEC-003": _decision("DEC-003"),
    }

    start = time.perf_counter()
    report = analyze_impact("REQ-001", entities)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 50, f"analyze_impact took {elapsed_ms:.2f}ms"
    affected_ids = {a.entity_id for a in report.affected}
    assert affected_ids == {"ASM-002", "DEC-003"}
    for affected in report.affected:
        assert affected.path[0] == "REQ-001"
        assert affected.path[-1] == affected.entity_id
        assert len(affected.path) >= 2


def test_impact_traversal_follows_multiple_hops():
    entities = {
        "REQ-001": _requirement("REQ-001", depends_on_assumptions=["ASM-002"]),
        "ASM-002": _assumption("ASM-002", affects_requirements=["REQ-005"]),
        "REQ-005": _requirement("REQ-005"),
    }

    report = analyze_impact("REQ-001", entities)

    by_id = {a.entity_id: a for a in report.affected}
    assert by_id["ASM-002"].hop_distance == 1
    assert by_id["REQ-005"].hop_distance == 2
    assert by_id["REQ-005"].path == ["REQ-001", "ASM-002", "REQ-005"]


def test_unrelated_entity_is_not_in_the_affected_list():
    entities = {
        "REQ-001": _requirement("REQ-001", depends_on_assumptions=["ASM-002"]),
        "ASM-002": _assumption("ASM-002"),
        "REQ-999": _requirement("REQ-999"),
    }

    report = analyze_impact("REQ-001", entities)

    assert "REQ-999" not in {a.entity_id for a in report.affected}


# ---------------------------------------------------------------------------
# Done when: a cyclic graph terminates and reports the cycle.
# ---------------------------------------------------------------------------


def test_cyclic_graph_terminates_and_reports_the_cycle():
    entities = {
        "REQ-001": _requirement("REQ-001", depends_on_assumptions=["ASM-002"]),
        "ASM-002": _assumption("ASM-002", affects_requirements=["REQ-001"]),
    }

    start = time.perf_counter()
    report = analyze_impact("REQ-001", entities)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 200, f"cyclic traversal took {elapsed_ms:.2f}ms"
    assert report.cycle is not None
    assert set(report.cycle) >= {"REQ-001", "ASM-002"}


def test_three_node_cycle_is_detected():
    entities = {
        "REQ-001": _requirement("REQ-001", depends_on_assumptions=["ASM-002"]),
        "ASM-002": _assumption("ASM-002", affects_requirements=["REQ-003"]),
        "REQ-003": _requirement("REQ-003", depends_on_assumptions=["ASM-002"]),
    }
    # REQ-001 -> ASM-002 -> REQ-003 -> ASM-002 is a cycle (ASM-002 <-> REQ-003).
    report = analyze_impact("REQ-001", entities)
    assert report.cycle is not None


def test_acyclic_graph_reports_no_cycle():
    entities = {
        "REQ-001": _requirement("REQ-001", depends_on_assumptions=["ASM-002"]),
        "ASM-002": _assumption("ASM-002"),
    }
    report = analyze_impact("REQ-001", entities)
    assert report.cycle is None


# ---------------------------------------------------------------------------
# Done when: impact on a 200-entity graph completes in under 200ms.
# ---------------------------------------------------------------------------


def test_impact_on_200_entity_graph_completes_under_200ms():
    # A 200-node chain: REQ-i -> DEC-i -> REQ-(i+1), via depends_on_decisions
    # / related_requirements, so the undirected graph is one connected path.
    entities: dict[str, Requirement | Decision] = {}
    for i in range(199):
        req_id = f"REQ-{i:03d}"
        dec_id = f"DEC-{i:03d}"
        entities[req_id] = _requirement(req_id, depends_on_decisions=[dec_id])
        next_req = f"REQ-{i + 1:03d}"
        entities[dec_id] = _decision(dec_id, related_requirements=[next_req])
    entities["REQ-199"] = _requirement("REQ-199")

    start = time.perf_counter()
    report = analyze_impact("REQ-000", entities)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 200, f"200-entity impact analysis took {elapsed_ms:.2f}ms"
    assert len(report.affected) == len(entities) - 1
