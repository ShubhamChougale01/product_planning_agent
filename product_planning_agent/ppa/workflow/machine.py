"""Global workflow state machine — loads `transitions.yaml`, queries it
(T20, DESIGN.md §2.5, S6.2).

The transition table is data; this module owns exactly the mechanics of
reading it and answering "is `frm -> to` legal," "what condition gates it,"
and "is `X` reachable from every state" — no workflow rule is ever encoded
as an `if`/`elif` chain here. Distinct from `ppa.ledger.transitions`
(T02/T03), which governs a single *entity's* status transitions — this
module governs the *global* workflow state the Orchestrator owns (§2.5's
own two-levels distinction, also documented in `ppa/validation/
workflow.py`'s own module docstring).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult

_TRANSITIONS_PATH = Path(__file__).parent / "transitions.yaml"


class IllegalWorkflowTransition(Exception):
    """Raised when `frm -> to` is not in the loaded transition table."""

    def __init__(self, frm: str, to: str, legal: frozenset[str]) -> None:
        self.frm = frm
        self.to = to
        self.legal = legal
        legal_desc = ", ".join(sorted(legal)) if legal else "(terminal — no legal transitions)"
        super().__init__(f"workflow: {frm!r} -> {to!r} is not a legal transition. Legal targets from {frm!r}: {legal_desc}")


def _load(path: Path | None = None) -> dict[str, Any]:
    text = (path or _TRANSITIONS_PATH).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    data.setdefault("states", [])
    data.setdefault("transitions", {})
    return data


_DATA = _load()
STATES: list[str] = _DATA["states"]
_RAW_TRANSITIONS: dict[str, list[dict[str, str]]] = _DATA["transitions"]

assert set(_RAW_TRANSITIONS) <= set(STATES), (
    "transitions.yaml names a transition source state that isn't in its own "
    "`states` list — the table is internally inconsistent."
)
assert all(
    row["to"] in STATES for rows in _RAW_TRANSITIONS.values() for row in rows
), "transitions.yaml names a transition target state that isn't in its own `states` list."


def legal_targets(state: str) -> frozenset[str]:
    """Every state `state` may legally move to next, per the loaded table.
    Empty for a state with no outgoing rows — terminal, or simply absent
    (every state in v1's own table has at least a `CHANGE_REQUESTED` row,
    per the reachability invariant below)."""

    return frozenset(row["to"] for row in _RAW_TRANSITIONS.get(state, []))


def condition_for(frm: str, to: str) -> str | None:
    """The named condition that gates `frm -> to`, or `None` if that move
    isn't in the table at all."""

    for row in _RAW_TRANSITIONS.get(frm, []):
        if row["to"] == to:
            return row.get("condition")
    return None


def validate_transition(frm: str, to: str) -> None:
    """Raise `IllegalWorkflowTransition` unless `frm -> to` is legal.
    `frm == to` is always legal — the same no-op-is-not-illegal rule
    `ppa.ledger.transitions.validate_transition` uses for entity status."""

    if frm == to:
        return
    legal = legal_targets(frm)
    if to not in legal:
        raise IllegalWorkflowTransition(frm, to, legal)


def check(frm: str, to: str) -> ToolResult | None:
    """`None` if `frm -> to` is legal; otherwise a `BUSINESS` `ToolResult`
    naming the rule that blocked it — the same envelope every validation
    layer in `ppa/validation/` returns, for a caller that wants a
    `ToolResult` rather than a caught exception."""

    try:
        validate_transition(frm, to)
    except IllegalWorkflowTransition as exc:
        rule = CATEGORY_RULES[ErrorCategory.BUSINESS]
        return ToolResult(
            success=False,
            error=ErrorInfo(
                category=ErrorCategory.BUSINESS,
                code="ILLEGAL_WORKFLOW_TRANSITION",
                is_retryable=bool(rule["is_retryable"]),
                recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
                description=str(exc),
                context={"validation_layer_failed": "workflow"},
            ),
        )
    return None


def is_reachable_from_every_state(target: str) -> bool:
    """`True` iff every state other than `target` itself has `target`
    among its legal targets — the property DESIGN.md §2.5 requires of
    `CHANGE_REQUESTED` specifically, stated generically so the test that
    checks it is checking the real function, not a hard-coded expectation."""

    return all(target in legal_targets(state) for state in STATES if state != target)
