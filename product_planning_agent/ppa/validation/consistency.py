"""Layer 5 — ledger consistency (DESIGN.md §2.13: "store, pre-append").

The last gate before anything is written: version mismatch, dangling
references and illegal status transitions. `check_transition` wraps
`ppa.ledger.transitions.validate_transition` (T02) — the same legal-move
matrix every entity type already declares — converting its
`IllegalTransition` exception into the same `ToolResult` shape every other
layer returns, so a caller never needs a `try/except` to tell a consistency
failure apart from a permission or schema one.

`ppa.tools.discovery_tools._generic_transition` (T16) calls this directly
rather than `validate_transition` on its own, so every `manage_*` status
change already routes through this layer in practice, not just in theory.
"""

from __future__ import annotations

from ppa.ledger.models import EntityType
from ppa.ledger.transitions import IllegalTransition, validate_transition
from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult

LAYER = "consistency"


def check_transition(entity_type: EntityType, frm: str, to: str) -> ToolResult | None:
    """`None` if `frm -> to` is legal for `entity_type` (including the
    always-legal `frm == to` no-op); otherwise a `BUSINESS` `ToolResult`
    naming the rule that blocked it."""

    try:
        validate_transition(entity_type, frm, to)
    except IllegalTransition as exc:
        rule = CATEGORY_RULES[ErrorCategory.BUSINESS]
        return ToolResult(
            success=False,
            error=ErrorInfo(
                category=ErrorCategory.BUSINESS,
                code="ILLEGAL_TRANSITION",
                is_retryable=bool(rule["is_retryable"]),
                recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
                description=str(exc),
                context={"validation_layer_failed": LAYER},
            ),
        )
    return None
