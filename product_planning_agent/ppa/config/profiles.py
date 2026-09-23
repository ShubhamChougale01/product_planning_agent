"""User profile and role-based criticality (DESIGN.md §6.1, S1.5).

Role drives question priority, not just vocabulary: an engineer can usually
answer `nfr`/`data`/`platform` directly from their own knowledge, but needs
Guidance Mode's help to articulate `success` in business terms — a product
person is the mirror image. `critical_areas()` is what turns that into an
actual gate: an area in the returned set cannot be left as an assumption on
the way to READY (DESIGN.md §6.4 — "Must confirm before READY: area is
critical"), regardless of impact.

**This table is an assumption, not something DESIGN.md spells out row by
row** — only the one engineer/product example sentence in §6.1 is given
verbatim. Filled in the same way T02's decision #7 handled a similar gap:
built to a defensible rule, flagged in `blockers.md` for confirmation rather
than buried here as if it were beyond question.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["engineer", "product", "mixed"]


class UserProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    technical_depth: Literal["high", "medium", "low"]
    domain_familiarity: Literal["high", "medium", "low"]


# Areas no profile may assume past — the anchoring risk is too high regardless
# of who's answering (DESIGN.md §6.4: "Must ask, never assume: problem, users").
ALWAYS_CRITICAL: set[str] = {"problem", "users"}

# Areas added on top of ALWAYS_CRITICAL, per role — the areas that role is
# expected to nail down directly rather than lean on Guidance Mode for.
_ROLE_CRITICAL_EXTRA: dict[Role, set[str]] = {
    "engineer": {"nfr", "data", "platform"},
    "product": {"success", "scope_in", "scope_out"},
    "mixed": {"nfr", "data", "platform", "success", "scope_in", "scope_out"},
}


def critical_areas(profile: UserProfile) -> set[str]:
    """Which of the twelve coverage areas this profile must confirm directly
    before a plan can reach READY. Keyed on `role` only for now —
    `technical_depth` and `domain_familiarity` don't yet narrow the set
    further; nothing in the design calls for that, and adding it speculatively
    would be a guess with no test to justify it."""

    return ALWAYS_CRITICAL | _ROLE_CRITICAL_EXTRA[profile.role]
