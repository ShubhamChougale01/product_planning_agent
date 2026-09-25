"""Coverage engine tests (T10). Every Done-when box in
tasks/t10_coverage_and_readiness_engines.md that concerns the coverage
engine maps to at least one test here.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import ppa.engines.coverage as coverage_module
from ppa.config.areas import AreaStatus
from ppa.config.profiles import UserProfile
from ppa.engines.coverage import compute_coverage, progress
from ppa.ledger.models import Assumption, Requirement

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _engineer() -> UserProfile:
    return UserProfile(role="engineer", technical_depth="high", domain_familiarity="high")


def _product() -> UserProfile:
    return UserProfile(role="product", technical_depth="low", domain_familiarity="high")


def _requirement(entity_id: str, *, status="PROPOSED", covers_areas=(), **overrides) -> Requirement:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        confidence="HIGH",
        confidence_basis="user said it directly",
        status=status,
        statement=f"statement for {entity_id}",
        type="functional",
        covers_areas=list(covers_areas),
        priority="must",
    )
    base.update(overrides)
    return Requirement(**base)


def _assumption(entity_id: str, *, status="PROPOSED", impact="MEDIUM", affects_areas=(), **overrides) -> Assumption:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        confidence="MEDIUM",
        confidence_basis="strongly implied",
        status=status,
        statement=f"assumption for {entity_id}",
        reason="inferred",
        impact=impact,
        affects_areas=list(affects_areas),
    )
    base.update(overrides)
    return Assumption(**base)


# ---------------------------------------------------------------------------
# compute_coverage's own state rules.
# ---------------------------------------------------------------------------


def test_area_with_no_covering_entity_is_untouched():
    coverage = compute_coverage({}, _engineer())
    assert coverage["problem"] == AreaStatus.UNTOUCHED


def test_area_covered_only_by_proposed_requirement_is_partial():
    entities = {"REQ-001": _requirement("REQ-001", status="PROPOSED", covers_areas=["problem"])}
    coverage = compute_coverage(entities, _engineer())
    assert coverage["problem"] == AreaStatus.PARTIAL


def test_area_covered_only_by_assumption_is_partial():
    entities = {"ASM-001": _assumption("ASM-001", affects_areas=["platform"])}
    coverage = compute_coverage(entities, _engineer())
    assert coverage["platform"] == AreaStatus.PARTIAL


def test_area_with_confirmed_requirement_is_sufficient():
    entities = {"REQ-001": _requirement("REQ-001", status="CONFIRMED", covers_areas=["data"])}
    coverage = compute_coverage(entities, _engineer())
    assert coverage["data"] == AreaStatus.SUFFICIENT


def test_area_with_confirmed_requirement_and_user_confirmation_is_confirmed():
    entities = {"REQ-001": _requirement("REQ-001", status="CONFIRMED", covers_areas=["data"])}
    coverage = compute_coverage(entities, _engineer(), confirmed_areas={"data"})
    assert coverage["data"] == AreaStatus.CONFIRMED


def test_confirmed_area_without_a_confirmed_requirement_stays_whatever_it_was():
    # Confirming an area in REVIEW that has no CONFIRMED requirement must not
    # fabricate SUFFICIENT/CONFIRMED out of nothing.
    entities = {"REQ-001": _requirement("REQ-001", status="PROPOSED", covers_areas=["data"])}
    coverage = compute_coverage(entities, _engineer(), confirmed_areas={"data"})
    assert coverage["data"] == AreaStatus.PARTIAL


# ---------------------------------------------------------------------------
# Done when: progress is reproducible from the event log alone.
# ---------------------------------------------------------------------------


def test_progress_is_reproducible_from_the_same_entities():
    entities = {
        "REQ-001": _requirement("REQ-001", status="CONFIRMED", covers_areas=["problem"]),
        "REQ-002": _requirement("REQ-002", status="CONFIRMED", covers_areas=["users"]),
    }
    profile = _engineer()

    first = progress(entities, profile)
    second = progress(dict(entities), profile)  # a fresh dict, same content

    assert first == second


# ---------------------------------------------------------------------------
# Done when: there is no public setter for coverage state — assert by
# inspection and by test.
# ---------------------------------------------------------------------------


def test_no_public_setter_is_exposed_from_the_coverage_module():
    functions_defined_here = {
        name
        for name, obj in inspect.getmembers(coverage_module, inspect.isfunction)
        if obj.__module__ == coverage_module.__name__ and not name.startswith("_")
    }
    assert functions_defined_here == {"compute_coverage", "progress"}
    assert coverage_module.__all__ == ["compute_coverage", "progress"]


# ---------------------------------------------------------------------------
# Done when: the same ledger yields different progress for engineer vs
# product profiles.
# ---------------------------------------------------------------------------


def test_same_ledger_yields_different_progress_for_different_profiles():
    # Engineer's critical set includes "platform"/"data"/"nfr" directly;
    # product's does not (ppa/config/profiles.py's _ROLE_CRITICAL_EXTRA).
    entities = {
        "REQ-001": _requirement("REQ-001", status="CONFIRMED", covers_areas=["platform", "data", "nfr"]),
    }

    engineer_progress = progress(entities, _engineer())
    product_progress = progress(entities, _product())

    assert engineer_progress != product_progress
    # Engineer: those three areas are all critical and all SUFFICIENT.
    assert engineer_progress[0] >= 3
    # Product doesn't count platform/data/nfr as critical at all, so its
    # denominator (and therefore the tuple) differs.
    assert engineer_progress[1] != product_progress[1] or engineer_progress[0] != product_progress[0]
