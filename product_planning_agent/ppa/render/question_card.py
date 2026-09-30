"""Question/answer renderer, now full (T17 + T31, DESIGN.md §1.4, §3.2,
§3.8, S5.6, S10.3-S10.4).

T17 proved the four answer affordances (`answered`, `dont_know`,
`decide_later`, `not_relevant`) round-trip through a human-readable
rendering. T31 adds the other half: `parse_answer` turns whatever a person
actually types at `ppa chat`'s prompt into one of those same four
affordances — the terminal's own input parser, kept here rather than in
`ppa/cli.py` because interpreting free text into the answer contract is a
rendering-adjacent concern, not I/O. `ask_user`/`answer_pending_question`
(`ppa/tools/interaction.py`) never call this themselves; they persist
whatever answer dict a caller already produced, from any surface.
"""

from __future__ import annotations

from typing import Any

_AFFORDANCE_HINT = "(you can also say: I don't know / decide later / not relevant)"

_ANSWER_LABELS: dict[str, str] = {
    "answered": "Answered",
    "dont_know": "I don't know",
    "decide_later": "Decide later",
    "not_relevant": "Not relevant",
}

_DONT_KNOW_PHRASES = {
    "idk", "i don't know", "i dont know", "dont know", "don't know", "not sure", "no idea",
}
_DECIDE_LATER_PHRASES = {"decide later", "later", "defer", "punt", "not now"}
_NOT_RELEVANT_PREFIXES = ("not relevant:", "not relevant -", "n/a:", "na:")


def parse_answer(raw: str) -> dict[str, Any]:
    """Free text typed at a terminal prompt -> one of the four affordance
    dicts `ask_user`/`answer_pending_question` accept. Whole-phrase matches
    only for `dont_know`/`decide_later` (so a real answer that happens to
    contain the word "later" is never misread) — everything else that isn't
    an explicit `not relevant: <reason>` is recorded as `answered` verbatim,
    the fail-safe direction: a person's real words are never silently
    discarded."""

    text = raw.strip()
    lowered = text.lower()

    if lowered in _DONT_KNOW_PHRASES:
        return {"answer_kind": "dont_know"}
    if lowered in _DECIDE_LATER_PHRASES:
        return {"answer_kind": "decide_later"}
    for prefix in _NOT_RELEVANT_PREFIXES:
        if lowered.startswith(prefix):
            reason = text[len(prefix):].strip() or "not relevant"
            return {"answer_kind": "not_relevant", "answer_text": reason}

    return {"answer_kind": "answered", "answer_text": text}


def render_question_card(question: dict[str, Any]) -> str:
    """`text`, `why_asked`, any `suggested_options`, and `recommended_
    default` with its one-line reason if given — everything a person needs
    to answer without asking "why does this matter?" first."""

    lines = [question["text"], f"  why: {question['why_asked']}"]

    options = question.get("suggested_options") or []
    if options:
        lines.append("  options: " + ", ".join(options))

    default = question.get("recommended_default")
    if default:
        reason = question.get("recommended_default_reason")
        suffix = f" ({reason})" if reason else ""
        lines.append(f"  default: {default}{suffix}")

    lines.append(f"  {_AFFORDANCE_HINT}")
    return "\n".join(lines)


def render_answer_summary(answer: dict[str, Any]) -> str:
    """One line per answer, however it was given — the same shape for all
    four affordances, so a transcript reads uniformly regardless of which
    one the user picked."""

    kind = answer.get("answer_kind")
    label = _ANSWER_LABELS.get(kind, str(kind))
    text = answer.get("answer_text")
    return f"{label}: {text}" if text else label
