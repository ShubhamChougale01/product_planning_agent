"""Result envelope and error taxonomy tests (T05). Every Done-when box in
tasks/t05_result_envelope_and_errors.md maps to at least one test here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ppa.results.categories import CATEGORY_RULES, ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult

# The fixed mapping table from the task, spelled out independently of
# CATEGORY_RULES so a bug in the source dict can't also hide from this test.
EXPECTED_TABLE: dict[ErrorCategory, tuple[bool, RecoveryAction]] = {
    ErrorCategory.TRANSIENT: (True, RecoveryAction.RETRY_SAME),
    ErrorCategory.VALIDATION: (False, RecoveryAction.CORRECT_AND_RETRY),
    ErrorCategory.BUSINESS: (False, RecoveryAction.CHANGE_WORKFLOW),
    ErrorCategory.PERMISSION: (False, RecoveryAction.ABORT_AND_ROUTE),
    ErrorCategory.NOT_IMPLEMENTED: (False, RecoveryAction.INFORM_USER),
}


def _error(category: ErrorCategory, **overrides) -> dict:
    is_retryable, action = EXPECTED_TABLE[category]
    base = dict(
        category=category,
        code="LEDGER_WRITE_TIMEOUT",
        is_retryable=is_retryable,
        retry_after_ms=None,
        description="something happened",
        recommended_action=action,
        context={},
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Done when: a test asserts the full mapping table exactly as written.
# ---------------------------------------------------------------------------


def test_category_rules_match_the_table_exactly():
    assert set(CATEGORY_RULES) == set(EXPECTED_TABLE)
    for category, (is_retryable, action) in EXPECTED_TABLE.items():
        rule = CATEGORY_RULES[category]
        assert rule["is_retryable"] is is_retryable
        assert rule["recommended_action"] is action


# ---------------------------------------------------------------------------
# Done when: constructing ErrorInfo without recommended_action raises.
# ---------------------------------------------------------------------------


def test_missing_recommended_action_raises():
    payload = _error(ErrorCategory.TRANSIENT)
    del payload["recommended_action"]
    with pytest.raises(ValidationError):
        ErrorInfo(**payload)


# ---------------------------------------------------------------------------
# Done when: a category/action pair outside the table raises.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category, wrong_action",
    [
        (ErrorCategory.TRANSIENT, RecoveryAction.INFORM_USER),
        (ErrorCategory.VALIDATION, RecoveryAction.RETRY_SAME),
        (ErrorCategory.BUSINESS, RecoveryAction.CORRECT_AND_RETRY),
        (ErrorCategory.PERMISSION, RecoveryAction.CHANGE_WORKFLOW),
        (ErrorCategory.NOT_IMPLEMENTED, RecoveryAction.ABORT_AND_ROUTE),
    ],
)
def test_wrong_recommended_action_for_category_raises(category, wrong_action):
    payload = _error(category, recommended_action=wrong_action)
    with pytest.raises(ValidationError):
        ErrorInfo(**payload)


@pytest.mark.parametrize("category", list(ErrorCategory))
def test_correct_pairing_for_every_category_constructs_cleanly(category):
    ErrorInfo(**_error(category))  # must not raise


# ---------------------------------------------------------------------------
# Done when: TRANSIENT is the only category with is_retryable=True.
# ---------------------------------------------------------------------------


def test_transient_is_the_only_retryable_category():
    retryable = {c for c in ErrorCategory if CATEGORY_RULES[c]["is_retryable"]}
    assert retryable == {ErrorCategory.TRANSIENT}


@pytest.mark.parametrize("category", [c for c in ErrorCategory if c is not ErrorCategory.TRANSIENT])
def test_non_transient_category_rejects_is_retryable_true(category):
    payload = _error(category, is_retryable=True)
    with pytest.raises(ValidationError):
        ErrorInfo(**payload)


def test_transient_rejects_is_retryable_false():
    payload = _error(ErrorCategory.TRANSIENT, is_retryable=False)
    with pytest.raises(ValidationError):
        ErrorInfo(**payload)


# ---------------------------------------------------------------------------
# Done when: success=True, result_count=0 is expressible and not an error.
# ---------------------------------------------------------------------------


def test_success_with_zero_results_is_not_an_error():
    result = ToolResult(success=True, result_count=0, data=[])
    assert result.success is True
    assert result.error is None
    assert result.result_count == 0


def test_success_with_data_and_nonzero_count():
    result = ToolResult(success=True, result_count=3, data=[1, 2, 3])
    assert result.result_count == 3


# ---------------------------------------------------------------------------
# Done when: degraded=True is expressible alongside success=True.
# ---------------------------------------------------------------------------


def test_degraded_success_is_expressible():
    result = ToolResult(success=True, degraded=True, result_count=1, data=["partial"])
    assert result.success is True
    assert result.degraded is True
    assert result.error is None


def test_degraded_defaults_to_false():
    result = ToolResult(success=True, result_count=0)
    assert result.degraded is False


# ---------------------------------------------------------------------------
# Envelope well-formedness: success and error must agree (follows directly
# from DESIGN.md §2.12's own JSON example and the "three states" rule, even
# though it isn't spelled out as its own Done-when box).
# ---------------------------------------------------------------------------


def test_success_true_cannot_carry_an_error():
    with pytest.raises(ValidationError):
        ToolResult(success=True, error=ErrorInfo(**_error(ErrorCategory.TRANSIENT)))


def test_success_false_must_carry_an_error():
    with pytest.raises(ValidationError):
        ToolResult(success=False)


def test_failure_result_round_trips():
    error = ErrorInfo(**_error(ErrorCategory.TRANSIENT, retry_after_ms=400))
    result = ToolResult(success=False, error=error)
    assert result.error.category is ErrorCategory.TRANSIENT
    assert result.error.retry_after_ms == 400


def test_result_and_error_reject_unknown_fields():
    with pytest.raises(ValidationError):
        ToolResult(success=True, result_count=0, unexpected="nope")
    with pytest.raises(ValidationError):
        ErrorInfo(**_error(ErrorCategory.TRANSIENT), unexpected="nope")
