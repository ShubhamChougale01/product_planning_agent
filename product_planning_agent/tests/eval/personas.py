"""Six scripted personas (T33, `tasks/t33_eval_fixtures_and_personas.md`).

Each persona is a **deterministic function from question to answer** — the
task's own explicit requirement. A persona is stateful only in the sense
that it remembers what it has already said this session (`contradicts_
self` needs that to contradict itself later); given the identical sequence
of questions, two fresh instances of the same persona always produce the
identical sequence of answers. `PERSONAS` maps a name to a zero-argument
factory, so a harness run always starts from a clean instance — nothing
here is a shared, mutable module-level object a second run could
accidentally inherit state from.

Every persona implements the same tiny protocol: `answer(question, *,
round_number) -> dict`, where `question` is a `QuestionAnswer` entity's own
`model_dump(mode="json")` shape (`text`, `why_asked`, `target_areas`,
`suggested_options`, `recommended_default`) and the returned dict is exactly
the `answer` shape `ppa.tools.interaction.ask_user`/`answer_pending_
question` already accept (`answer_kind`, plus `answer_text`/`dont_know_kind`
where that kind needs one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class Persona(Protocol):
    name: str

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]: ...


def _primary_area(question: dict[str, Any]) -> str:
    areas = question.get("target_areas") or []
    return areas[0] if areas else "this"


# ---------------------------------------------------------------------------
# knows_their_stuff — detailed, consistent answers.
# ---------------------------------------------------------------------------


@dataclass
class KnowsTheirStuff:
    """Answers every question directly and specifically — takes the
    recommended default or first suggested option when one is offered
    (a real expert usually agrees with a well-reasoned proposal), otherwise
    states a concrete, area-grounded answer. Never says "I don't know,"
    never defers."""

    name: str = "knows_their_stuff"

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        default = question.get("recommended_default")
        options = question.get("suggested_options") or []
        area = _primary_area(question)
        if default:
            text = f"{default} — that's the right call for {area}."
        elif options:
            text = f"{options[0]}, definitely — we've thought this through for {area}."
        else:
            text = (
                f"Here's exactly how {area} should work: we've scoped it precisely and "
                "there's no ambiguity left on our end."
            )
        return {"answer_kind": "answered", "answer_text": text}


# ---------------------------------------------------------------------------
# vague — short, non-committal answers.
# ---------------------------------------------------------------------------


@dataclass
class Vague:
    """Answers every question, but with the least committal text possible
    — never `dont_know` (a vague person still technically answers), never
    a real specification either."""

    name: str = "vague"

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        return {"answer_kind": "answered", "answer_text": "I guess whatever's easiest — up to you, really."}


# ---------------------------------------------------------------------------
# always_idk — "I don't know" to everything.
# ---------------------------------------------------------------------------


@dataclass
class AlwaysIDK:
    """The stress test for T26's anti-loop guard: every single question,
    regardless of content, gets the bare `dont_know` affordance with no
    kind supplied — the hardest case for the router to classify, and the
    one a session must still terminate against rather than loop forever."""

    name: str = "always_idk"

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        return {"answer_kind": "dont_know"}


# ---------------------------------------------------------------------------
# contradicts_self — round 4 contradicts round 1.
# ---------------------------------------------------------------------------


@dataclass
class ContradictsSelf:
    """Answers consistently and concretely — like `knows_their_stuff` —
    for the first three times a given area comes up, then, from round 4
    onward, deliberately reverses its own earlier position on the *first*
    area it already committed to (T30's own contradiction-must-be-caught
    case). Deterministic: which area gets reversed, and when, depends only
    on the order areas were first seen, never on randomness."""

    name: str = "contradicts_self"
    _first_answer_by_area: dict[str, str] = field(default_factory=dict)
    _reversed_area: str | None = None

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        area = _primary_area(question)
        options = question.get("suggested_options") or []
        default = question.get("recommended_default")
        first_choice = default or (options[0] if options else f"the straightforward approach for {area}")

        if area not in self._first_answer_by_area:
            self._first_answer_by_area[area] = first_choice
            return {"answer_kind": "answered", "answer_text": f"{first_choice} — locking that in for {area}."}

        if round_number >= 4 and self._reversed_area is None:
            self._reversed_area = area
            original = self._first_answer_by_area[area]
            reversal = options[1] if len(options) > 1 and options[1] != original else f"the opposite of what we said before about {area}"
            return {
                "answer_kind": "answered",
                "answer_text": f"Actually, forget what I said earlier — we're going with {reversal} for {area} instead.",
            }

        # Already reversed, or not yet round 4: restate the standing answer.
        return {"answer_kind": "answered", "answer_text": f"Still {self._first_answer_by_area[area]}, as before, for {area}."}


# ---------------------------------------------------------------------------
# impatient — "just build it," pushes to skip.
# ---------------------------------------------------------------------------


@dataclass
class Impatient:
    """Never gives real content — always pushes to defer, testing that the
    readiness gate holds even when a person is actively trying to rush
    past it. `decide_later` every time: the honest affordance for "I don't
    want to answer this right now," never a fabricated answer."""

    name: str = "impatient"

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        return {"answer_kind": "decide_later"}


# ---------------------------------------------------------------------------
# defers_to_client — "that's the client's call."
# ---------------------------------------------------------------------------


@dataclass
class DefersToClient:
    """Every question gets pushed to an outside party, in the client's own
    words — the raw affordance a real person would give; classifying that
    into `needs_external_input` and producing the questionnaire (T27) is
    the *agent's* job, not this persona's, per `ppa.tools.interaction.
    ask_user`'s own docstring ("`dont_know_kind` classification is T26's
    job")."""

    name: str = "defers_to_client"

    def answer(self, question: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        return {
            "answer_kind": "dont_know",
            "answer_text": "That's not my decision to make — you'll need to check with the client on that one.",
        }


PERSONAS: dict[str, Callable[[], Persona]] = {
    "knows_their_stuff": KnowsTheirStuff,
    "vague": Vague,
    "always_idk": AlwaysIDK,
    "contradicts_self": ContradictsSelf,
    "impatient": Impatient,
    "defers_to_client": DefersToClient,
}
"""One factory per persona, keyed by name — `tasks/t33_eval_fixtures_and_
personas.md`'s own table, verbatim. Always call the factory for a fresh
instance; never share one across sessions."""
