"""Error taxonomy (DESIGN.md §2.12, S1.7).

Five categories, each with a fixed `is_retryable` value and a fixed
`recommended_action`. The mapping lives here as data so `ppa/results/
envelope.py` can enforce it in a validator rather than trust every call site
to get it right.

`is_retryable` answers exactly one question: will sending this identical
request again likely succeed? It is advisory. `recommended_action` is the
contract callers actually branch on — see the module docstring in
`envelope.py` for why that distinction matters.
"""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    TRANSIENT = "TRANSIENT"
    VALIDATION = "VALIDATION"
    BUSINESS = "BUSINESS"
    PERMISSION = "PERMISSION"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class RecoveryAction(str, Enum):
    RETRY_SAME = "RETRY_SAME"
    CORRECT_AND_RETRY = "CORRECT_AND_RETRY"
    CHANGE_WORKFLOW = "CHANGE_WORKFLOW"
    ABORT_AND_ROUTE = "ABORT_AND_ROUTE"
    INFORM_USER = "INFORM_USER"


CATEGORY_RULES: dict[ErrorCategory, dict[str, object]] = {
    ErrorCategory.TRANSIENT: {
        "is_retryable": True,
        "recommended_action": RecoveryAction.RETRY_SAME,
    },
    ErrorCategory.VALIDATION: {
        "is_retryable": False,
        "recommended_action": RecoveryAction.CORRECT_AND_RETRY,
    },
    ErrorCategory.BUSINESS: {
        "is_retryable": False,
        "recommended_action": RecoveryAction.CHANGE_WORKFLOW,
    },
    ErrorCategory.PERMISSION: {
        "is_retryable": False,
        "recommended_action": RecoveryAction.ABORT_AND_ROUTE,
    },
    ErrorCategory.NOT_IMPLEMENTED: {
        "is_retryable": False,
        "recommended_action": RecoveryAction.INFORM_USER,
    },
}

assert set(CATEGORY_RULES) == set(ErrorCategory), (
    "Every ErrorCategory must have a fixed rule — a category missing here "
    "would let ErrorInfo construct with an unenforced is_retryable/"
    "recommended_action pair."
)

assert {c for c, rule in CATEGORY_RULES.items() if rule["is_retryable"]} == {
    ErrorCategory.TRANSIENT
}, "TRANSIENT must be the only category with is_retryable=True."
