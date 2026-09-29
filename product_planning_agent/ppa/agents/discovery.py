"""Discovery Agent — the v1 intelligence layer (T20 protocol, T23 the first
real system prompt and turn behavior, DESIGN.md §1.5, §2.5, §6.1, §6.4,
S7.1-S7.3).

**Two levels of state, per DESIGN.md §2.5.** The global workflow state
(`DISCOVERY`, `DISCOVERY_VALIDATED`, ...) is the Orchestrator's, already
built (T20/T21). `DiscoveryMode` below is the *other* one — Discovery's own
internal state machine (`INTAKE -> CLARIFY <-> GUIDANCE -> RESEARCH ->
REVIEW -> READY`), which the Orchestrator's outer loop never needs to know
about: it is invisible outside this module and `ppa.agents.turn`.

**Mode-scoped tools are enforced at the harness level, not by prompt text**
(this task's own explicit instruction) — `MODE_TOOLS` is a real, checked
subset of `ppa.agents.registry.GRANTS["discovery"]`, and
`allowed_tools_for_mode` is what `ppa.agents.turn` actually passes to
`ClaudeAgentOptions.allowed_tools`. A mode not granting `ask_user` means the
model genuinely cannot call it — verified live, not assumed (see bug #5,
`blockers.md`, found while wiring this up: `allowed_tools` needs the
fully-qualified `mcp__<server>__<tool>` form, a bare name silently grants
nothing).

GUIDANCE and RESEARCH modes get no prompt fragment of their own here — they
are subagent hand-offs (`request_guidance`), built out properly in T28/T29.
Their tool subsets are deliberately minimal placeholders until then.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import StrictUndefined, Template

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent
from ppa.config.profiles import Role, UserProfile

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

_PROMPTS_DIR = Path(__file__).parent / "prompts"

SYSTEM_PROMPT_PLACEHOLDER = "Discovery Agent — real system prompt built in T23."
"""Kept as a module constant for backward reference (earlier tasks'
comments point at this name), but `DiscoveryAgent.system_prompt` below no
longer uses it as its value — `render_system_prompt` is what actually runs
now."""


class DiscoveryMode(str, Enum):
    """Discovery's own internal state machine (DESIGN.md §2.5) — distinct
    from, and invisible to, the Orchestrator's global workflow state."""

    INTAKE = "INTAKE"
    CLARIFY = "CLARIFY"
    GUIDANCE = "GUIDANCE"
    RESEARCH = "RESEARCH"
    REVIEW = "REVIEW"
    READY = "READY"


DEFAULT_MODE = DiscoveryMode.INTAKE
"""A fresh project starts in INTAKE — nothing has been asked yet."""

_DISCOVERY_GRANT_SUBSET: dict[DiscoveryMode, frozenset[str]] = {
    DiscoveryMode.INTAKE: frozenset(
        {"read_planning_state", "manage_requirement", "manage_assumption", "manage_decision", "manage_unknown", "ask_user"}
    ),
    DiscoveryMode.CLARIFY: frozenset(
        {
            "read_planning_state",
            "manage_requirement",
            "manage_assumption",
            "manage_decision",
            "manage_unknown",
            "ask_user",
            "request_guidance",
        }
    ),
    # Placeholder subsets — GUIDANCE/RESEARCH are real subagent hand-offs
    # built in T28/T29. Discovery's own grant has exactly one hand-off tool
    # (`request_guidance`) today; there is no separate research hand-off
    # tool yet, so both stay read-only-plus-handoff until then.
    DiscoveryMode.GUIDANCE: frozenset({"read_planning_state", "request_guidance"}),
    DiscoveryMode.RESEARCH: frozenset({"read_planning_state", "request_guidance"}),
    # REVIEW: nothing left to *draft* or *ask* — `ask_user` stays out, on
    # purpose (mode_review.md's own instruction: no question tool here,
    # by design). But T30's own job is walking HIGH-impact unconfirmed
    # assumptions one at a time (confirm/reject/modify), which needs
    # `manage_assumption` — the one write REVIEW genuinely does. Approval
    # itself is explicitly *not* a tool call (see `ppa.agents.modes.
    # review.grant_review_approval`'s own docstring for why — the same
    # "no agent is ever granted a tool to approve its own request" rule
    # `ppa/tools/approval.py` already established for T18).
    DiscoveryMode.REVIEW: frozenset({"read_planning_state", "manage_assumption"}),
    # READY: nothing left to draft, ask, or confirm. Read-only by design,
    # not by omission — this is what makes "cannot call manage_requirement
    # (create) in READY" true without needing a special case anywhere else.
    DiscoveryMode.READY: frozenset({"read_planning_state"}),
}


def allowed_tools_for_mode(mode: DiscoveryMode, *, agent_id: str = "discovery") -> frozenset[str]:
    """The tools actually usable in `mode` — the mode's own subset,
    intersected with `agent_id`'s real grant, so a mode table typo can
    never *widen* what the agent may do beyond `ppa.agents.registry.GRANTS`,
    only narrow it further.

    Deferred import: `ppa.agents.registry` imports this module (for
    `DiscoveryAgent`), so a module-level import here would be circular
    whenever `ppa.agents.discovery` happens to be the first of the two
    imported in a process — the same pattern `ppa.agents.base.BaseAgent.
    grant()` already uses for exactly this reason."""

    from ppa.agents.registry import grant_for

    return _DISCOVERY_GRANT_SUBSET[mode] & grant_for(agent_id)


_MODE_FRAGMENT_FILES: dict[DiscoveryMode, str] = {
    DiscoveryMode.INTAKE: "mode_intake.md",
    DiscoveryMode.CLARIFY: "mode_clarify.md",
    DiscoveryMode.REVIEW: "mode_review.md",
}
"""GUIDANCE/RESEARCH/READY have no fragment of their own: GUIDANCE and
RESEARCH are subagent hand-offs with their own prompts (T28/T29); READY
needs no further instruction beyond its own (already minimal) tool
subset — there is nothing left to tell the agent to do."""

ROLE_VOCABULARY: dict[Role, str] = {
    "engineer": (
        "This person can answer `platform`, `data` and `nfr` questions directly and precisely — "
        "ask them plainly, in engineering terms. On `problem`, `users`, `success` and `rollout`, "
        "they may need help translating their own knowledge into product terms — offer a "
        "proposal to react to, and route to Guidance Mode if they genuinely have not thought "
        "about it yet."
    ),
    "product": (
        "This person can answer `problem`, `users`, `jobs`, `scope_in`, `scope_out`, `success` "
        "and `rollout` directly, in product terms. On `platform`, `data` and `nfr`, expect to "
        "route to Guidance Mode or a research query rather than a confident, precise answer from "
        "this profile — do not penalize them for deferring a technical question."
    ),
    "mixed": (
        "No single area of expertise is guaranteed here — treat every area as potentially "
        "needing a proposal to react to, and do not assume fluency on either the product or the "
        "engineering side without evidence from what this person has actually said."
    ),
}


def _read_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def render_system_prompt(
    mode: DiscoveryMode,
    profile: UserProfile,
    *,
    today: date | None = None,
) -> str:
    """`discovery_core.md`, rendered with today's date and role vocabulary,
    plus `mode`'s own fragment appended — the whole prompt this task's
    Done-when box requires to "render differently for engineer and product
    profiles" and to inject the current date on every turn."""

    today = today or date.today()
    core_template = Template(_read_prompt("discovery_core.md"), undefined=StrictUndefined)
    core = core_template.render(
        current_date=today.isoformat(),
        role=profile.role,
        technical_depth=profile.technical_depth,
        domain_familiarity=profile.domain_familiarity,
        role_vocabulary=ROLE_VOCABULARY[profile.role],
        mode=mode.value,
    )

    fragment_file = _MODE_FRAGMENT_FILES.get(mode)
    if fragment_file is None:
        return core
    return f"{core}\n\n{_read_prompt(fragment_file)}"


class DiscoveryAgent(BaseAgent):
    id = "discovery"
    system_prompt = SYSTEM_PROMPT_PLACEHOLDER
    """Kept as a static placeholder — the real, per-turn prompt depends on
    mode/profile/date and is built by `render_system_prompt` inside
    `ppa.agents.turn.run_discovery_turn`, not read from this attribute."""

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        from ppa.agents.turn import run_discovery_turn

        return run_discovery_turn(ctx)
