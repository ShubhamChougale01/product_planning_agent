"""Don't-know classification and routing table (T26, DESIGN.md §1.6, §3.3,
§3.4, S8.1-S8.3).

Matching a user's free-text non-answer ("what do you mean?", "whatever you
think") to one of the seven kinds is inherently qualitative — the model's
own job, guided by `mode_clarify.md`'s routing table, exactly the way
`ppa.engines.question_engine` leaves candidate generation and the
qualitative half of its filter to the model. What this module owns
outright, as deterministic code rather than prose a prompt author has to
get right every time:

- the seven kinds, named once (`DONT_KNOW_KINDS`) — never restated ad hoc
  in a prompt or a test fixture;
- the routing table each kind maps to (`ROUTE_FOR_KIND`), so "no_opinion
  routes to ASSUMPTION" is a fact asserted against code, not prose that can
  drift from what the writer tools actually do;
- which two kinds justify an expensive path (`EXPENSIVE_KINDS`) — "only
  unexplored and factually_unknown" is the task's own explicit rule;
- the anti-loop guard's arithmetic (S8.3): counting reframe attempts and
  deciding when to force escalation is deterministic even though the
  content of a reframe is not, exactly like `question_engine.detect_
  fatigue` is deterministic arithmetic over the model's own answer-kind
  classifications.
"""

from __future__ import annotations

from typing import Literal

DontKnowKind = Literal[
    "dont_understand",
    "no_opinion",
    "depends_on_x",
    "not_my_call",
    "unexplored",
    "factually_unknown",
    "needs_external_input",
]

DONT_KNOW_KINDS: tuple[DontKnowKind, ...] = (
    "dont_understand",
    "no_opinion",
    "depends_on_x",
    "not_my_call",
    "unexplored",
    "factually_unknown",
    "needs_external_input",
)

ROUTE_FOR_KIND: dict[DontKnowKind, str] = {
    "dont_understand": "REFRAME",
    "no_opinion": "ASSUMPTION",
    "depends_on_x": "REORDER",
    "not_my_call": "DECISION",
    "unexplored": "GUIDANCE",
    "factually_unknown": "RESEARCH",
    "needs_external_input": "EXTERNAL_QUESTIONNAIRE",
}
"""DESIGN.md §3.4's own routing table (S8.2), named once here rather than
restated as prose in a prompt for the model to reinterpret differently
each time — the same "named once, in code" discipline `ppa.config.
autonomy` already applies to the assume/ask threshold."""

EXPENSIVE_KINDS: frozenset[DontKnowKind] = frozenset({"unexplored", "factually_unknown"})
"""Only these two kinds justify Guidance Mode or Research — the task's own
"only unexplored and factually_unknown justify the expensive paths" line,
named as a set so a test can assert `dont_understand` is never in it
rather than re-deriving the claim from `ROUTE_FOR_KIND` by hand."""

MAX_REFRAME_ATTEMPTS = 2
"""DESIGN.md §3.5: Guidance Mode is triggered "on unexplored ... or after
two failed reframings" — the same threshold the anti-loop guard (S8.3)
uses generically, not only for the unexplored -> Guidance path. A question
may be asked once, reframed once, reframed a second time — a third
non-answer forces escalation rather than a fourth ask in any form."""

FORCED_ESCALATION_ROUTE: DontKnowKind = "unexplored"
"""S8.3: after `MAX_REFRAME_ATTEMPTS` reframes still return a non-answer,
the anti-loop guard forces the same route `unexplored` already uses
(Guidance Mode, via `Unknown.route="GUIDANCE"`) — a user who genuinely
cannot answer no matter how the question is reframed is functionally
indistinguishable from one who has "honestly not thought about it yet"."""


def should_force_escalation(reframe_attempts: int) -> bool:
    """`True` once `reframe_attempts` (reframes of *this* question already
    made, not counting the original ask) has reached `MAX_REFRAME_ATTEMPTS`
    — the point at which the agent must never ask the same question a
    third time and must instead escalate to `FORCED_ESCALATION_ROUTE`."""

    return reframe_attempts >= MAX_REFRAME_ATTEMPTS


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def is_same_question(a: str, b: str) -> bool:
    """Whitespace/case-insensitive identity check — the deterministic half
    of "never re-ask the same question in the same form"
    (`discovery_core.md`). A genuine reframing changes the wording; this
    only catches the degenerate case of the exact same text asked twice,
    which is exactly what the anti-loop guard must never allow to happen
    silently."""

    return _normalize(a) == _normalize(b)


def simulate_always_idk_termination(*, max_asks: int = 6) -> list[str]:
    """Deterministic proof of S8.3's anti-loop guard: a user who answers
    `dont_know` to *every* question must still reach a terminal state — a
    tracked, routed item — within a bounded number of asks, never an
    unbounded loop.

    Returns the sequence of question texts the engine would ask about one
    stuck gap, in order — `["Original question", "Reframe 1", "Reframe 2"]`
    for `MAX_REFRAME_ATTEMPTS=2` — stopping the instant
    `should_force_escalation` fires rather than producing a fourth ask.
    `max_asks` is only a safety bound in case a future edit to the
    threshold constants breaks termination; it is never expected to bind.

    This proves the routing *engine's own arithmetic* — reframe counting
    and the forced-escalation threshold — deterministically, without a real
    persona or a live model turn. It is not a substitute for T33/T34's own
    scripted, persona-driven session (the `always_idk` persona itself is
    that later infrastructure's own artifact) — see blockers.md for the
    decision logged against this exact gap, the same honesty T25's decision
    #33 already applied to its own session-level Done-when boxes.
    """

    asked: list[str] = ["Original question"]
    reframe_attempts = 0
    while not should_force_escalation(reframe_attempts):
        reframe_attempts += 1
        candidate = f"Reframe {reframe_attempts}"
        if any(is_same_question(candidate, prior) for prior in asked):
            raise AssertionError(f"anti-loop guard failure: {candidate!r} would repeat a prior ask")
        asked.append(candidate)
        if len(asked) > max_asks:  # pragma: no cover - defensive only
            raise AssertionError("anti-loop guard failure: exceeded max_asks without escalating")
    return asked


SIGNAL_EXAMPLES: dict[DontKnowKind, str] = {
    "dont_understand": "What do you mean by that?",
    "no_opinion": "Whatever you think is best.",
    "depends_on_x": "Depends on the budget.",
    "not_my_call": "That's the CTO's decision, not mine.",
    "unexplored": "Honestly, I haven't thought about that at all.",
    "factually_unknown": "I don't know, which database scales better here?",
    "needs_external_input": "That's the client's call, not mine to make.",
}
"""DESIGN.md §1.6's own worked examples, named once here as the canonical
fixture data both `tests/eval/test_dont_know.py` and `mode_clarify.md`'s
prompt text are written against — a prompt author restating these by hand
risks drifting from what the tests actually assert."""
