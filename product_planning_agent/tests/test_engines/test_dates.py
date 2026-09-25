"""Date rules tests (T12). Every Done-when box in
tasks/t12_date_rules_and_open_items.md that concerns `ppa/engines/dates.py`
maps to at least one test here.
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta, timezone

from freezegun import freeze_time

import ppa.engines.dates as dates_module
from ppa.engines.dates import due_within, expected_decision_date, is_overdue

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)

_DATETIME_NOW_CALL = re.compile(r"datetime\.now\(")


class _Decision:
    """A minimal `decision.blocking` / `decision.affects` duck-type double —
    `expected_decision_date` doesn't require a real `Decision` entity."""

    def __init__(self, blocking: bool, affects: str | None):
        self.blocking = blocking
        self.affects = affects


# ---------------------------------------------------------------------------
# Done when: the tier rule is stated in one readable place and is
# overridable.
# ---------------------------------------------------------------------------


def test_blocking_architecture_gets_three_days():
    assert expected_decision_date(_Decision(True, "architecture"), NOW) == NOW + timedelta(days=3)


def test_blocking_scope_gets_five_days():
    assert expected_decision_date(_Decision(True, "scope"), NOW) == NOW + timedelta(days=5)


def test_non_blocking_gets_fourteen_days_regardless_of_affects():
    assert expected_decision_date(_Decision(False, "architecture"), NOW) == NOW + timedelta(days=14)
    assert expected_decision_date(_Decision(False, "other"), NOW) == NOW + timedelta(days=14)


def test_blocking_other_falls_back_to_fourteen_days():
    # Only "architecture" and "scope" get the shorter tiers; a blocking
    # decision that affects neither still gets the plain +14 day default,
    # not a silent architecture-tier guess.
    assert expected_decision_date(_Decision(True, "other"), NOW) == NOW + timedelta(days=14)


def test_blocking_unclassified_affects_falls_back_to_fourteen_days():
    # decision #21: affects=None (unclassified) must never be silently
    # guessed at "architecture" or "scope" — it reads as "other".
    assert expected_decision_date(_Decision(True, None), NOW) == NOW + timedelta(days=14)


def test_the_rule_is_stated_in_one_readable_place():
    rule = dates_module.EXPECTED_DECISION_DATE_RULE
    assert "3 days" in rule
    assert "5 days" in rule
    assert "14 days" in rule


def test_rule_result_is_a_plain_overridable_value():
    result = expected_decision_date(_Decision(True, "architecture"), NOW)
    overridden = result + timedelta(days=100)
    assert overridden != result


# ---------------------------------------------------------------------------
# is_overdue / due_within.
# ---------------------------------------------------------------------------


def test_is_overdue_true_for_past_due_date():
    assert is_overdue(NOW - timedelta(days=1), NOW) is True


def test_is_overdue_false_for_future_due_date():
    assert is_overdue(NOW + timedelta(days=1), NOW) is False


def test_is_overdue_false_for_no_due_date():
    assert is_overdue(None, NOW) is False


class _Item:
    def __init__(self, due_date):
        self.due_date = due_date


def test_is_overdue_accepts_an_item_with_a_due_date_attribute():
    assert is_overdue(_Item(NOW - timedelta(days=1)), NOW) is True
    assert is_overdue(_Item(None), NOW) is False


def test_due_within_includes_items_in_the_window():
    items = [_Item(NOW + timedelta(days=1)), _Item(NOW + timedelta(days=10)), _Item(None)]
    result = due_within(items, 3, NOW)
    assert len(result) == 1
    assert result[0].due_date == NOW + timedelta(days=1)


def test_due_within_excludes_already_overdue_items():
    items = [_Item(NOW - timedelta(days=1))]
    assert due_within(items, 3, NOW) == []


# ---------------------------------------------------------------------------
# Done when: all date tests pass with a frozen clock (freezegun).
# ---------------------------------------------------------------------------


@freeze_time("2026-09-25 09:00:00")
def test_functions_are_correct_under_a_frozen_clock():
    frozen_now = datetime.now(timezone.utc)
    assert frozen_now == NOW

    assert expected_decision_date(_Decision(True, "scope"), frozen_now) == NOW + timedelta(days=5)
    assert is_overdue(frozen_now - timedelta(hours=1), frozen_now) is True


# ---------------------------------------------------------------------------
# Done when: no engine function calls datetime.now() internally — grep and
# assert.
# ---------------------------------------------------------------------------


def test_no_engine_function_calls_the_real_clock():
    source = inspect.getsource(dates_module)
    assert not _DATETIME_NOW_CALL.search(source), (
        "ppa/engines/dates.py must never call datetime.now() — every date "
        "computation takes `now` as a parameter"
    )
