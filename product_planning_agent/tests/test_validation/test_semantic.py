"""Layer 4 — semantic validation (T16). `ppa/validation/semantic.py` stays a
stub until T19 centralizes all five layers (see that task's own file); for
now the one semantic rule this build needs — a Requirement cannot be
CONFIRMED while a blocking Unknown covering the same area is still OPEN —
lives directly in `ppa.tools.discovery_tools._requirement_confirm_semantic_
check`. These tests exercise that rule in isolation, at the function level,
so a regression here is caught independently of the full writer round-trip
covered by `tests/test_tools/test_writers.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.ledger.models import Requirement, Unknown
from ppa.results.categories import ErrorCategory
from ppa.tools.discovery_tools import (
    _open_blocking_unknowns_for_areas,
    _requirement_confirm_semantic_check,
)

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _requirement(entity_id: str, covers_areas: list[str]) -> Requirement:
    return Requirement(
        id=entity_id, version=1, created_at=NOW, updated_at=NOW,
        created_by="user:shubham", updated_by="user:shubham", history=[],
        confidence="HIGH", confidence_basis="user said it",
        status="PROPOSED", statement="statement", type="functional",
        covers_areas=covers_areas, priority="must",
    )


def _unknown(entity_id: str, area: str, *, blocking: bool, status: str, owner_type: str = "user") -> Unknown:
    return Unknown(
        id=entity_id, version=1, created_at=NOW, updated_at=NOW,
        created_by="user:shubham", updated_by="user:shubham", history=[],
        status=status, question="question", area=area, why_it_matters="it matters",
        blocking=blocking, route="USER_DECISION", owner_type=owner_type,
    )


def test_open_blocking_unknowns_for_areas_finds_a_match_in_the_same_area():
    entities = {"UNK-001": _unknown("UNK-001", "existing_system", blocking=True, status="OPEN")}
    assert _open_blocking_unknowns_for_areas(entities, ["existing_system"]) == ["UNK-001"]


def test_open_blocking_unknowns_for_areas_ignores_a_different_area():
    entities = {"UNK-001": _unknown("UNK-001", "existing_system", blocking=True, status="OPEN")}
    assert _open_blocking_unknowns_for_areas(entities, ["jobs"]) == []


def test_open_blocking_unknowns_for_areas_ignores_a_non_blocking_unknown():
    entities = {"UNK-001": _unknown("UNK-001", "existing_system", blocking=False, status="OPEN")}
    assert _open_blocking_unknowns_for_areas(entities, ["existing_system"]) == []


def test_open_blocking_unknowns_for_areas_ignores_a_resolved_unknown():
    entities = {"UNK-001": _unknown("UNK-001", "existing_system", blocking=True, status="RESOLVED")}
    assert _open_blocking_unknowns_for_areas(entities, ["existing_system"]) == []


def test_requirement_confirm_semantic_check_rejects_when_area_is_blocked():
    requirement = _requirement("REQ-001", ["existing_system"])
    entities = {
        "REQ-001": requirement,
        "UNK-001": _unknown("UNK-001", "existing_system", blocking=True, status="OPEN"),
    }
    result = _requirement_confirm_semantic_check(entities, requirement, {})
    assert result is not None
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "AREA_BLOCKED"
    assert "UNK-001" in result.error.context["blocking_unknowns"]


def test_requirement_confirm_semantic_check_allows_when_no_area_is_blocked():
    requirement = _requirement("REQ-001", ["jobs"])
    entities = {
        "REQ-001": requirement,
        "UNK-001": _unknown("UNK-001", "existing_system", blocking=True, status="OPEN"),
    }
    assert _requirement_confirm_semantic_check(entities, requirement, {}) is None


def test_requirement_confirm_semantic_check_covering_multiple_areas_names_every_blocker():
    requirement = _requirement("REQ-001", ["jobs", "existing_system"])
    entities = {
        "REQ-001": requirement,
        "UNK-001": _unknown("UNK-001", "existing_system", blocking=True, status="OPEN"),
        "UNK-002": _unknown("UNK-002", "jobs", blocking=True, status="OPEN"),
    }
    result = _requirement_confirm_semantic_check(entities, requirement, {})
    assert result is not None
    assert set(result.error.context["blocking_unknowns"]) == {"UNK-001", "UNK-002"}
