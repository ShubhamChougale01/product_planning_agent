"""Question engine — deciding what *not* to ask (DESIGN.md §1.4, §3.2,
§6.4, S7.5).

Five steps in the design (A find gaps, B generate candidates, C filter, D
score/select, E shape); only A, C's own numeric rules, D and the budget
constants are things a deterministic function can own outright. B
(generating a candidate question from a coverage gap) and the qualitative
half of C (is this specific candidate "agent_inference-confidence>=MEDIUM",
"research", or genuinely blocking?) are the model's own job — nothing here
reads ledger free text to make that call for it. This module gives the
model the deterministic inputs (which areas are gaps, ranked) and the
scoring formula to apply, exactly like `ppa.config.autonomy` gives it the
assume/ask threshold: named once, in code, never restated as numbers in a
prompt for the model to reinterpret.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ppa.config.areas import AREA_KEYS, AreaStatus
from ppa.config.profiles import UserProfile, critical_areas
from ppa.engines.coverage import compute_coverage
from ppa.ledger.models import BaseEntity

MAX_QUESTIONS_PER_ROUND = 5
TARGET_QUESTIONS_PER_ROUND = 3
"""DESIGN.md §1.4: "Hard cap: max 5 questions per round, target 3.\""""

FATIGUE_THRESHOLD = 3
"""Three consecutive non-answers in a row switches to assumption-heavy
mode, automatically, and the agent must say so (§1.4)."""

SOFT_CAP_ROUND = 4
"""After round 4, the agent must either pass the readiness gate or offer to
close the rest with assumptions — never just keep asking silently (§1.4)."""


def find_gaps(
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    *,
    confirmed_areas: set[str] | None = None,
) -> list[str]:
    """Coverage areas below `SUFFICIENT`, ranked critical-for-this-profile
    first, then by `ppa.config.areas.AREA_KEYS`'s own declared order within
    each tier — deterministic, so two runs against the same ledger always
    rank gaps identically. This is step A of the pipeline; step B (turning
    a gap into an actual candidate question) is the model's job."""

    coverage = compute_coverage(entities, profile, confirmed_areas=confirmed_areas)
    critical = critical_areas(profile)
    gaps = [area for area in AREA_KEYS if coverage[area] not in (AreaStatus.SUFFICIENT, AreaStatus.CONFIRMED)]
    return sorted(gaps, key=lambda area: (area not in critical, AREA_KEYS.index(area)))


def question_priority(*, blocking: bool, information_gain: float, user_answerability: float, cognitive_cost: float) -> float:
    """DESIGN.md §3.2 step D's own formula, as code rather than something
    the model computes itself:

    ```
    priority = (2.0 if blocking else 1.0)
             × information_gain
             × user_answerability
             ÷ cognitive_cost
    ```

    `cognitive_cost` must be `> 0` — a zero-cost question is a modeling
    error upstream (every real question costs the user *something* to
    answer), not a case this function silently divides around.
    """

    if cognitive_cost <= 0:
        raise ValueError(f"cognitive_cost must be > 0, got {cognitive_cost!r}")
    weight = 2.0 if blocking else 1.0
    return weight * information_gain * user_answerability / cognitive_cost


def select_top_questions(
    candidates: Sequence[Mapping[str, Any]], *, max_questions: int = MAX_QUESTIONS_PER_ROUND
) -> list[Mapping[str, Any]]:
    """Sort `candidates` (each a mapping with at least a `"priority"` key,
    e.g. `question_priority`'s own output) by priority descending and take
    the top `max_questions` — "top 3, max 5" enforced by code, not by the
    model remembering to stop partway through a longer list it generated."""

    return sorted(candidates, key=lambda c: c["priority"], reverse=True)[:max_questions]


def detect_fatigue(recent_answer_kinds: Sequence[str]) -> bool:
    """DESIGN.md §1.4's fatigue signal: the most recent `FATIGUE_THRESHOLD`
    answers all being a non-answer (`"dont_know"`) means switch to
    assumption-heavy mode, automatically, and announce it — never grind
    through the rest of a question list as if nothing changed."""

    if len(recent_answer_kinds) < FATIGUE_THRESHOLD:
        return False
    return all(kind == "dont_know" for kind in recent_answer_kinds[-FATIGUE_THRESHOLD:])


def should_offer_assumptions(round_number: int, *, ready: bool) -> bool:
    """After `SOFT_CAP_ROUND`, if the readiness gate has not passed, the
    agent must offer to close the rest with assumptions rather than simply
    keep asking — DESIGN.md §1.4's soft cap."""

    return round_number >= SOFT_CAP_ROUND and not ready
