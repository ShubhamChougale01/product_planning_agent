"""User profile and role-based criticality tests (T04)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ppa.config.areas import AREA_KEYS
from ppa.config.profiles import UserProfile, critical_areas


def _profile(role: str) -> UserProfile:
    return UserProfile(role=role, technical_depth="medium", domain_familiarity="medium")


def test_engineer_and_product_get_different_critical_sets():
    engineer = critical_areas(_profile("engineer"))
    product = critical_areas(_profile("product"))
    assert engineer != product


def test_engineer_and_product_still_share_the_never_assume_areas():
    engineer = critical_areas(_profile("engineer"))
    product = critical_areas(_profile("product"))
    assert {"problem", "users"} <= engineer
    assert {"problem", "users"} <= product


def test_engineer_critical_set_covers_the_design_example():
    """DESIGN.md §6.1: an engineer answers nfr/data/platform directly."""
    engineer = critical_areas(_profile("engineer"))
    assert {"nfr", "data", "platform"} <= engineer


def test_product_critical_set_covers_the_design_example():
    """DESIGN.md §6.1: product inverts — success is their strong suit, not
    the engineer's."""
    product = critical_areas(_profile("product"))
    assert "success" in product


def test_mixed_role_is_a_superset_of_engineer_and_product_extras():
    mixed = critical_areas(_profile("mixed"))
    engineer = critical_areas(_profile("engineer"))
    product = critical_areas(_profile("product"))
    assert engineer <= mixed
    assert product <= mixed


def test_every_critical_area_is_a_real_coverage_area():
    for role in ("engineer", "product", "mixed"):
        assert critical_areas(_profile(role)) <= set(AREA_KEYS)


def test_unknown_role_is_rejected_at_construction():
    with pytest.raises(ValidationError):
        UserProfile(role="designer", technical_depth="medium", domain_familiarity="medium")


def test_profile_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        UserProfile(
            role="engineer",
            technical_depth="medium",
            domain_familiarity="medium",
            seniority="staff",
        )
