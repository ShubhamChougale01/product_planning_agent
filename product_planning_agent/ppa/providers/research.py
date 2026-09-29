"""ResearchProvider seam and degradation path (T29, DESIGN.md §6.5, §2.12,
S9.4-S9.5).

Absence must degrade honestly, never stall planning and never fabricate a
confident answer. Three states, three distinct behaviours — deliberately
**not** a bare try/except around a search call, because "no capability at
all" and "a real search that failed" are different facts the user needs
told differently (§6.5's own worked example):

- **AVAILABLE** — research runs; the caller writes a real `RES-nnn` with
  real sources and `researched_at`.
- **UNAVAILABLE** — `available()` was `False` before anything was
  attempted. The agent states plainly that it cannot research here, offers
  its own best (unverified) answer, and sets `degraded=True`.
- **FAILED** — a real attempt raised. Retried once by the caller; if the
  retry also fails, treated as UNAVAILABLE but with a *different* message —
  a failed search is not the same situation as no search capability at all.

Decision #5 (`blockers.md`) already confirmed web search works under this
build's own subscription auth — `SdkWebSearchResearchProvider.available()`
therefore returns `True` in this environment. The `Protocol` and the
`UNAVAILABLE`/`FAILED` machinery exist so a *different* auth path (or a
future outage) degrades honestly instead of this module having to change.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

Outcome = str
"""`"AVAILABLE" | "UNAVAILABLE" | "FAILED"` — plain `str`, not a stricter
`Literal`, only because `ResearchResult` below is what actually enforces
the three legal values; kept simple since nothing outside this module
constructs one directly."""


class ResearchResult(BaseModel):
    """One provider call's outcome. `message` is always the plain-language
    line the agent says to the user — never omitted, regardless of
    `outcome` — so a caller never has to invent user-facing prose itself."""

    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    degraded: bool = False
    message: str
    summary: str | None = None
    options_found: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: str | None = None


class ResearchProvider(Protocol):
    def available(self) -> bool: ...

    def research(self, question: str, context: str) -> ResearchResult: ...


def unavailable_result(*, degraded_answer: str) -> ResearchResult:
    """§6.5's own exact line: *"I can't research this here. From what I
    know: <degraded answer>. Worth verifying."* `degraded_answer` is
    supplied by the caller (the model's own best guess) — this function
    never invents one, it only assembles the honest framing around it."""

    return ResearchResult(
        outcome="UNAVAILABLE",
        degraded=True,
        message=f"I can't research this here. From what I know: {degraded_answer} Worth verifying.",
    )


def failed_result(*, detail: str, degraded_answer: str) -> ResearchResult:
    """A real attempt failed (after one retry) — distinct wording from
    `unavailable_result`'s, per §6.5's own instruction that these are
    different situations for the user."""

    return ResearchResult(
        outcome="FAILED",
        degraded=True,
        message=(
            f"I tried to research this and the search failed ({detail}). From what I know: "
            f"{degraded_answer} Worth verifying — I could not confirm it just now."
        ),
    )


def empty_result(*, question: str) -> ResearchResult:
    """A real, successful search that legitimately found nothing worth
    reporting — success, not an error, and never retried (an empty result
    is not a failure the way a raised exception is)."""

    return ResearchResult(
        outcome="AVAILABLE",
        degraded=False,
        message=f"I searched for this and found nothing conclusive: {question!r}. Nothing further to report.",
        summary="No relevant results found.",
    )


class NullResearchProvider:
    """Always `UNAVAILABLE` — the honest default for a caller that has not
    wired a real provider at all (e.g. an auth path without web search).
    Never fabricates its own "from what I know" — a real caller supplies
    that, since only the model reasoning about the actual question has one
    to offer."""

    def available(self) -> bool:
        return False

    def research(self, question: str, context: str) -> ResearchResult:  # noqa: ARG002 - Protocol shape
        return unavailable_result(degraded_answer="nothing — no research capability is available for this call")


class SdkWebSearchResearchProvider:
    """The real provider this build actually uses. `available()` is a
    static `True` in this environment (decision #5) — the real research
    itself does not happen through `.research()` at all, it happens inside
    `ppa.agents.subagents.research`'s own isolated SDK turn (the model
    calls `WebSearch` and `manage_research` directly, the same "own turn,
    own tools" shape T28's Guidance subagent already established).
    `.research()` exists so this class still satisfies the `Protocol` and
    so a *test* double can stand in for it without needing a real turn."""

    def available(self) -> bool:
        return True

    def research(self, question: str, context: str) -> ResearchResult:  # noqa: ARG002 - not this class's real path
        raise NotImplementedError(
            "SdkWebSearchResearchProvider.research() is not the real research path — "
            "ppa.agents.subagents.research.run_research_session runs its own SDK turn instead."
        )
