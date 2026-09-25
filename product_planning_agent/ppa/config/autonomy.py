"""Autonomy thresholds — DESIGN.md §6.4, §1.5.

**A table, not prose.** "Never silently decide important product
requirements" is the right instinct, but "important" is exactly the word an
LLM interprets generously in whichever direction is convenient. This module
is what `ppa/agents/prompts/discovery_core.md` points at instead of
restating the numbers — tuning the threshold is a data change here, never a
prompt edit (DESIGN.md's own build-impact note for §6.4: "folded into S7.5
as an explicit threshold table rather than prompt prose").

Added here rather than in this task's own "Files touched" list because
nothing else in the codebase owns this table yet — the same "no filename
named, so it needs a home" gap blocker #2/#3 and decision #23 already found
in earlier tasks. See decision #30, `blockers.md`.
"""

from __future__ import annotations

from typing import Literal

AutonomyLevel = Literal["conservative", "balanced", "assertive"]
ImpactLevel = Literal["LOW", "MEDIUM", "HIGH"]

DEFAULT_AUTONOMY: AutonomyLevel = "balanced"

_IMPACT_RANK: dict[ImpactLevel, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

ASSUME_THRESHOLD: dict[AutonomyLevel, ImpactLevel] = {
    "conservative": "LOW",
    "balanced": "LOW",
    "assertive": "MEDIUM",
}
"""The maximum impact level (inclusive) that may be silently assumed in a
non-critical area, per autonomy setting. `conservative` and `balanced` are
numerically identical — DESIGN.md §6.4 describes `conservative`'s own rule
("assumes only LOW-impact non-critical items") in exactly the words the
unqualified default table already uses, and names only `assertive` as an
actual deviation ("will assume MEDIUM in non-critical areas"). Nothing in
the design text describes a third, stricter number for `conservative` to
hold that `balanced` (the stated default) does not already hold — inventing
one would be a guess this module refuses to make. It never changes the
never-silent rule either way: every assumption is still recorded and
surfaced, only whether it may be recorded *without asking first* shifts."""

NEVER_ASSUME_AREAS = frozenset({"problem", "users"})
"""DESIGN.md §6.4's own exception to propose-and-confirm, not merely to the
assume/confirm threshold: a wrong proposal here anchors the user badly, so
these two areas are always asked outright — `may_assume_silently` returns
`False` for them regardless of impact, criticality or autonomy setting."""


def may_assume_silently(
    *,
    impact: ImpactLevel,
    area: str,
    is_critical: bool,
    autonomy: AutonomyLevel = DEFAULT_AUTONOMY,
) -> bool:
    """`True` iff the agent may record this as a silent assumption
    (`user_confirmation_required=True`, per T16's own writer contract) and
    move on, rather than asking the user directly.

    Never a byte of prose in the prompt reimplements this — the prompt
    names this function/module, the boundary is enforced here."""

    if area in NEVER_ASSUME_AREAS:
        return False
    if is_critical:
        return False
    return _IMPACT_RANK[impact] <= _IMPACT_RANK[ASSUME_THRESHOLD[autonomy]]
