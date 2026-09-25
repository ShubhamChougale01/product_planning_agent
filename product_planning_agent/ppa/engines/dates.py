"""Date rules — all date arithmetic lives here, never in the model
(DESIGN.md §1.12, §1.13, S4.4).

The model does not reliably know today's date and will confabulate it, so
**every function here takes `now` as a parameter.** None of them ever reads
the real system clock internally — that is what makes this module testable
with a frozen clock, and it is enforced by
`tests/test_engines/test_dates.py`'s own source-grep, not just a comment.

`expected_decision_date` is a stated, overridable v1 tier rule, not a guess:
a date the user did not set and cannot explain is noise, so the rule that
produced it must always be inspectable in one place (`EXPECTED_DECISION_
DATE_RULE`, below).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal, Sequence

AffectsKind = Literal["architecture", "scope", "other"]
"""DESIGN.md's tier rule names "affects architecture" / "affects scope" as
the deciding factor for a *blocking* decision's deadline, but `Decision`
(T02) carries no field that classifies which — only a free-text `question`.
Rather than guess from that text, this is accepted as an explicit argument:
whoever calls `expected_decision_date` (T21's outer loop, eventually) is in
a better position to judge it — from the decision's `related_requirements`
and the areas they cover, say — than a keyword match on a sentence would
be. Flagged in `blockers.md` for confirmation, same posture as the ledger's
other "accept it as an input, don't invent a derivation" calls."""

EXPECTED_DECISION_DATE_RULE = (
    "blocking + affects architecture -> now + 3 days; "
    "blocking + affects scope -> now + 5 days; "
    "otherwise -> now + 14 days (v1 has no phase timeline to derive a "
    "tighter or looser date from)"
)
"""The v1 tier rule (§1.13), stated in exactly one readable place so it can
be shown to the user verbatim next to any date this module produces, and so
that date is always overridable rather than mistaken for something the
model decided. DESIGN.md also allows a non-blocking decision to get `null`
with "before build starts" instead of +14 days, for when a real phase
timeline exists — v1 has none yet, so `expected_decision_date` always takes
the concrete +14-day substitute, never that `null` branch."""


def expected_decision_date(*, blocking: bool, affects: AffectsKind, now: datetime) -> datetime:
    """The v1 tier rule, applied at `now`. Always a concrete datetime —
    see `EXPECTED_DECISION_DATE_RULE`'s docstring for why the `null` branch
    DESIGN.md also allows is never taken here."""

    if blocking and affects == "architecture":
        return now + timedelta(days=3)
    if blocking and affects == "scope":
        return now + timedelta(days=5)
    return now + timedelta(days=14)


def _due_date_of(item: Any) -> datetime | None:
    return item.due_date if hasattr(item, "due_date") else item


def is_overdue(item: Any, now: datetime) -> bool:
    """`item` is either a bare due-date `datetime | None`, or anything
    carrying a `.due_date` attribute (an `OpenItem`, for instance) — the
    same duck typing `due_within` uses below. `False` for "no due date at
    all": nothing is overdue against a deadline that was never set."""

    due = _due_date_of(item)
    return due is not None and due < now


def due_within(items: Sequence[Any], days: int, now: datetime) -> list[Any]:
    """Every item in `items` whose due date falls in `[now, now + days]`,
    inclusive. Already-overdue items are excluded — `is_overdue` is the
    check for those; this one answers "coming up," not "coming up or
    already missed.\""""

    cutoff = now + timedelta(days=days)
    result = []
    for item in items:
        due = _due_date_of(item)
        if due is not None and now <= due <= cutoff:
            result.append(item)
    return result
