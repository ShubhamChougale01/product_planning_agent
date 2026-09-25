"""Autonomy threshold tests (T23, DESIGN.md §6.4). See decision #30,
`blockers.md`, for why `conservative` and `balanced` are numerically
identical here.
"""

from __future__ import annotations

import pytest

from ppa.config.autonomy import ASSUME_THRESHOLD, DEFAULT_AUTONOMY, NEVER_ASSUME_AREAS, may_assume_silently


def test_default_autonomy_is_balanced():
    assert DEFAULT_AUTONOMY == "balanced"


def test_conservative_and_balanced_share_the_same_threshold():
    assert ASSUME_THRESHOLD["conservative"] == ASSUME_THRESHOLD["balanced"] == "LOW"


def test_assertive_raises_the_threshold_to_medium():
    assert ASSUME_THRESHOLD["assertive"] == "MEDIUM"


@pytest.mark.parametrize("area", sorted(NEVER_ASSUME_AREAS))
def test_never_assume_areas_are_never_silently_assumable(area):
    assert may_assume_silently(impact="LOW", area=area, is_critical=False) is False
    assert may_assume_silently(impact="LOW", area=area, is_critical=False, autonomy="assertive") is False


def test_low_impact_non_critical_area_may_be_assumed_by_default():
    assert may_assume_silently(impact="LOW", area="platform", is_critical=False) is True


def test_medium_impact_requires_confirmation_under_balanced():
    assert may_assume_silently(impact="MEDIUM", area="platform", is_critical=False) is False


def test_medium_impact_may_be_assumed_under_assertive():
    assert may_assume_silently(impact="MEDIUM", area="platform", is_critical=False, autonomy="assertive") is True


def test_high_impact_is_never_silently_assumable_at_any_autonomy_level():
    for level in ("conservative", "balanced", "assertive"):
        assert may_assume_silently(impact="HIGH", area="platform", is_critical=False, autonomy=level) is False


def test_critical_area_always_requires_confirmation_regardless_of_impact():
    assert may_assume_silently(impact="LOW", area="constraints", is_critical=True) is False
    assert may_assume_silently(impact="LOW", area="constraints", is_critical=True, autonomy="assertive") is False
