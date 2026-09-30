"""`ppa client-questions` — the client questionnaire renderer (T27,
DESIGN.md §6.2, S8.4).

Every `owner_type == "external"` `Unknown` is one open item the *client*,
not the user at the keyboard, must answer — rendered here as a sendable
document, grouped by coverage area, in language a client can read with no
internal jargon and no entity id ever printed. The `Unknown` carries the
question, why it matters, its area and whether it is blocking; the
provisional assumption standing in for an answer (`ppa.tools.discovery_
tools.manage_assumption(create, provisional=True, ...)`, T26) is looked up
through `Unknown.converted_to` (T02's own field for exactly this: "the id
of the entity this Unknown turned into") — no new schema field, no new
link table, just the field DESIGN.md already gave this relationship.

Honors house style (T04) for the document's own title and terminology —
never for the entity schema, which stays fixed per §6.3. `style.export.
format` is read for the shipped default (`markdown`); nothing in this
codebase implements a `json`/`jira_csv` export path yet (see `StoryStyle`'s
own "declared now so v1 doesn't block it" precedent) — recorded as a real
scope gap, not silently ignored, see `t27_external_input_questionnaire.md`'s
own Build record.
"""

from __future__ import annotations

from typing import Mapping

from ppa.config.areas import AREA_KEYS, AREAS
from ppa.config.house_style import HouseStyle
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import Assumption, BaseEntity, EntityType, Unknown

_AREA_LABELS: dict[str, str] = {area.key: area.label for area in AREAS}


def _external_open_items(entities: Mapping[str, BaseEntity]) -> list[Unknown]:
    """Every `Unknown` a client, not the user, owns — regardless of
    `status`, so an item still awaiting its provisional assumption (not yet
    `converted_to` anything) still appears rather than silently vanishing
    from the document mid-session."""

    return [
        entity
        for entity_id, entity in entities.items()
        if entity_type_for(entity_id) is EntityType.UNKNOWN and entity.owner_type == "external"
    ]


def _provisional_statement(unknown: Unknown, entities: Mapping[str, BaseEntity]) -> str | None:
    converted_to = unknown.converted_to
    if not converted_to:
        return None
    linked = entities.get(converted_to)
    if linked is None or entity_type_for(converted_to) is not EntityType.ASSUMPTION:
        return None
    assert isinstance(linked, Assumption)
    return linked.statement


def render_client_questionnaire(entities: Mapping[str, BaseEntity], style: HouseStyle) -> str:
    """One markdown document, grouped by coverage area in `AREA_KEYS`'s own
    declared order, covering every external-owned open item. Never prints
    an entity id, a `route`/`owner_type` literal, or any other internal
    vocabulary — every line is written for a client to read cold."""

    items = _external_open_items(entities)
    lines = [f"# {style.name.replace('_', ' ').title()} — Questions for you", ""]

    if not items:
        lines.append("No open questions for you right now.")
        return "\n".join(lines) + "\n"

    lines.append(
        "The items below need your input before planning can finish. Each one shows what we'll "
        "assume in the meantime if we don't hear back — so silence still has a stated consequence, "
        "never a silent guess."
    )

    by_area: dict[str, list[Unknown]] = {}
    for item in items:
        by_area.setdefault(item.area, []).append(item)

    for area_key in AREA_KEYS:
        area_items = by_area.get(area_key)
        if not area_items:
            continue
        lines.append("")
        lines.append(f"## {_AREA_LABELS.get(area_key, area_key)}")
        for item in sorted(area_items, key=lambda u: (not u.blocking, u.question)):
            lines.append("")
            lines.append(f"### {item.question}")
            lines.append(f"- **Why it matters:** {item.why_it_matters}")
            provisional = _provisional_statement(item, entities)
            lines.append(
                f"- **What we'll assume until you confirm:** {provisional}"
                if provisional
                else "- **What we'll assume until you confirm:** not yet recorded"
            )
            lines.append(f"- **Blocking:** {'Yes' if item.blocking else 'No'}")

    return "\n".join(lines) + "\n"
