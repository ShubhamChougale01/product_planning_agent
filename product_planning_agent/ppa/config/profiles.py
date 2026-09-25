"""User profile and role-based criticality (DESIGN.md §6.1, S1.5).

Role drives question priority, not just vocabulary: an engineer can usually
answer `nfr`/`data`/`platform` directly from their own knowledge, but needs
Guidance Mode's help to articulate `success` in business terms — a product
person is the mirror image. `critical_areas()` is what turns that into an
actual gate: an area in the returned set cannot be left as an assumption on
the way to READY (DESIGN.md §6.4 — "Must confirm before READY: area is
critical"), regardless of impact.

**This table mirrors DESIGN.md §6.1's own "Engineer answers directly /
Product answers directly / Neither → route" table exactly** (all twelve
areas — that table was missed when this module was first built; see
blockers.md decision #11 for the correction). "Direct" for a role means
that area belongs in `_ROLE_CRITICAL_EXTRA` for the role; "needs
guidance"/"partial" means routed to Guidance Mode instead, not forced
critical for that role.
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
# Matches DESIGN.md §6.1's table exactly, row by row:
#   problem, users, jobs      -> engineer needs guidance, product direct
#   scope_in, scope_out       -> both direct
#   success                   -> engineer needs guidance, product direct
#   constraints               -> engineer direct, product partial
#   existing_system           -> engineer direct, product needs guidance
#   platform, data, nfr       -> engineer direct, product needs guidance
#   rollout                   -> engineer needs guidance, product direct
_ROLE_CRITICAL_EXTRA: dict[Role, set[str]] = {
    "engineer": {"scope_in", "scope_out", "constraints", "existing_system", "platform", "data", "nfr"},
    "product": {"problem", "users", "jobs", "scope_in", "scope_out", "success", "rollout"},
    "mixed": {
        "scope_in", "scope_out", "constraints", "existing_system", "platform", "data", "nfr",
        "problem", "users", "jobs", "success", "rollout",
    },
}


def critical_areas(profile: UserProfile) -> set[str]:
    """Which of the twelve coverage areas this profile must confirm directly
    before a plan can reach READY. Keyed on `role` only for now —
    `technical_depth` and `domain_familiarity` don't yet narrow the set
    further; nothing in the design calls for that, and adding it speculatively
    would be a guess with no test to justify it."""

    return ALWAYS_CRITICAL | _ROLE_CRITICAL_EXTRA[profile.role]
