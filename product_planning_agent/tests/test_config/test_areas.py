"""Coverage area tests (T04)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ppa.config.areas import AREA_KEYS, AREAS, AREAS_BY_KEY, AreaStatus, CoverageArea

EXPECTED_KEYS = [
    "problem",
    "users",
    "jobs",
    "scope_in",
    "scope_out",
    "success",
    "constraints",
    "existing_system",
    "platform",
    "data",
    "nfr",
    "rollout",
]


def test_twelve_areas_defined():
    assert len(AREAS) == 12
    assert AREA_KEYS == EXPECTED_KEYS


def test_every_area_has_a_label_description_and_probe_hints():
    for area in AREAS:
        assert area.label
        assert area.description
        assert isinstance(area.probe_hints, list)


def test_areas_by_key_matches_areas():
    assert set(AREAS_BY_KEY) == set(AREA_KEYS)
    for key, area in AREAS_BY_KEY.items():
        assert area.key == key


def test_area_status_progression_is_left_to_right():
    assert [s.value for s in AreaStatus] == ["UNTOUCHED", "PARTIAL", "SUFFICIENT", "CONFIRMED"]


def test_area_has_no_criticality_field():
    """Criticality is a per-profile lookup (ppa/config/profiles.py), never a
    fixed field on the area itself — this is a T04 design constraint, not an
    oversight, so assert the field doesn't exist rather than just not using it."""
    assert "critical" not in CoverageArea.model_fields
    assert "criticality" not in CoverageArea.model_fields


def test_area_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CoverageArea(key="x", label="X", description="d", critical=True)


def test_areas_are_editable_without_touching_logic():
    """Data, not code — constructing a new area doesn't require any engine
    changes. Simulates a config edit."""
    custom = CoverageArea(key="new_area", label="New", description="d", probe_hints=["?"])
    assert custom.key == "new_area"
