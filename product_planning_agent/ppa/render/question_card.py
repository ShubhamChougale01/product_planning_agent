"""Minimal question/answer renderer (T17, DESIGN.md §1.4, §3.2, S5.6).

The real interactive CLI surface is built in T31 — this module only needs
to prove the four answer affordances (`answered`, `dont_know`,
`decide_later`, `not_relevant`) round-trip through a human-readable
rendering, not drive an actual terminal prompt loop yet. `ask_user`
(`ppa/tools/interaction.py`) never calls these itself; they exist so a
caller (a test today, T31's real CLI tomorrow) can turn a question/answer
dict into something a person can read.
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
