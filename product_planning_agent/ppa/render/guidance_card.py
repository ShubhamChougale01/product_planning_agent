"""Render a `GuidanceBrief` conversationally, and answer `ppa why <dec-id>`
from the ledger alone (T28, DESIGN.md §1.7, §3.5, S9.1-S9.3).

**"The main agent renders this conversationally. It never dumps JSON at the
user."** — the task's own explicit instruction. `render_guidance_brief`
turns a validated `GuidanceBrief` (`ppa.agents.subagents.guidance`) into
prose a person reads like a colleague explaining a trade-off, not a payload
inspection. `render_why` is the other half of persistence paying off: once
a `ResearchFinding`'s `feeds_decision` links it to the `Decision` it
resolved (`manage_research(operation="link_decision")`, T28), "why did we
choose this?" is answerable from the ledger alone, long after the
conversation that produced it is gone.
"""

from __future__ import annotations

from typing import Mapping

from ppa.agents.subagents.guidance import GuidanceBrief
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, Decision, EntityType, ResearchFinding


def render_guidance_brief(brief: GuidanceBrief) -> str:
    """One brief, as prose — every field the schema carries, none of it as
    raw JSON. Confidence is stated in plain words, not a bare enum value."""

    lines = [
        brief.restated_plainly,
        "",
        f"**Why it matters:** {brief.why_it_matters}",
    ]
    if brief.what_it_affects:
        lines.append(f"**This affects:** {', '.join(brief.what_it_affects)}")

    lines.append("")
    lines.append("**Options:**")
    for option in brief.options:
        lines.append(f"- **{option.name}** — {option.description}")
        if option.pros:
            lines.append(f"  - Pros: {', '.join(option.pros)}")
        if option.cons:
            lines.append(f"  - Cons: {', '.join(option.cons)}")
        lines.append(f"  - Best when: {option.best_when}")

    rec = brief.recommendation
    confidence_word = {"HIGH": "high confidence", "MEDIUM": "medium confidence", "LOW": "low confidence"}[rec.confidence]
    lines.append("")
    lines.append(f"**My recommendation ({confidence_word}):** {rec.option} — {rec.because}")

    if brief.researched and brief.sources:
        lines.append("")
        lines.append("**Sources:** " + "; ".join(brief.sources))

    lines.append("")
    lines.append(f"**What would settle this for good:** {brief.what_would_settle_it}")
    lines.append(
        f"**If we defer this instead:** we'll assume {brief.safe_default_if_deferred!r} until it's "
        "decided for real, so planning keeps moving."
    )

    return "\n".join(lines)


def render_why(dec_id: str, entities: Mapping[str, BaseEntity]) -> str:
    """"Why did we choose this?" — from `entities` alone, no conversation
    replay needed. Looks up `dec_id`, then every `ResearchFinding` whose
    `feeds_decision` names it (`manage_research(operation="link_decision")`,
    T28)."""

    decision = entities.get(dec_id)
    if decision is None or entity_type_for(dec_id) is not EntityType.DECISION:
        return f"No decision {dec_id!r} found in this project's ledger."
    assert isinstance(decision, Decision)

    lines = [f"# {dec_id}: {decision.question}", "", f"**Status:** {decision.status}"]

    if decision.status == "DECIDED":
        lines.append(f"**Chosen:** {decision.chosen_option}")
        if decision.rationale:
            lines.append(f"**Why:** {decision.rationale}")
    elif decision.status == "DECIDE_LATER":
        lines.append(f"**Deferred:** {decision.defer_reason or 'no reason recorded'}")
        if decision.current_assumption:
            assumption = entities.get(decision.current_assumption)
            if assumption is not None:
                lines.append(f"**Assumption standing in meanwhile:** {assumption.statement}")

    findings = [
        e for eid, e in entities.items()
        if entity_type_for(eid) is EntityType.RESEARCH_FINDING and getattr(e, "feeds_decision", None) == dec_id
    ]
    if findings:
        lines.append("")
        lines.append("**Research behind this decision:**")
        for finding in findings:
            assert isinstance(finding, ResearchFinding)
            lines.append(f"- {finding.question} — {finding.summary}")
            if finding.sources:
                lines.append(f"  Sources: {'; '.join(finding.sources)}")

    return "\n".join(lines)
