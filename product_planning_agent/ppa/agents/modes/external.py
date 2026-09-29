"""External-input routing's own shape contract (T27, DESIGN.md §6.2, S8.4).

`needs_external_input` (T26) already records a provisional `Assumption`
(`provisional=True`, `user_confirmation_required=True`). What T27 adds is
the *open item* half of DESIGN.md §6.2's route diagram — an `Unknown` with
`owner_type="external"`, which is what the readiness gate's own condition 2
exception (already built, T10) and `ppa.render.client_questions` both key
on — linked to its provisional Assumption via `Unknown.converted_to` (T02),
never a new field. Like every other mode's shape contract in this package,
this checks the *ledger state* a round actually wrote, never the model's
own claimed text.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import Assumption, BaseEntity, EntityType, Unknown


class ExternalInputReport(BaseModel):
    """One `needs_external_input` round's routing, checked against
    `tasks/t27_external_input_questionnaire.md`'s own Done-when boxes."""

    model_config = ConfigDict(extra="forbid")

    open_item_count: int
    linked_to_provisional_assumption_count: int
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def _new_ids(before: Mapping[str, BaseEntity], after: Mapping[str, BaseEntity], entity_type: EntityType) -> list[str]:
    return [eid for eid in after if eid not in before and entity_type_for(eid) is entity_type]


def evaluate_external_input_round(
    entities_before: Mapping[str, BaseEntity],
    entities_after: Mapping[str, BaseEntity],
) -> ExternalInputReport:
    """Diffs `entities_before`/`entities_after` (both `ppa.ledger.
    materialize.current_entities`'s own shape). A correctly-routed
    `needs_external_input` answer must produce exactly the pair DESIGN.md
    §6.2's route diagram names: an external-owned `Unknown` open item, and
    a provisional `Assumption` it points to via `converted_to` — never one
    without the other, and never a silent, unflagged assumption instead."""

    violations: list[str] = []

    new_unknowns = _new_ids(entities_before, entities_after, EntityType.UNKNOWN)
    new_assumptions = _new_ids(entities_before, entities_after, EntityType.ASSUMPTION)

    external_items: list[Unknown] = []
    for eid in new_unknowns:
        entity = entities_after[eid]
        assert isinstance(entity, Unknown)
        if entity.owner_type == "external":
            external_items.append(entity)

    if not external_items:
        violations.append("no Unknown(owner_type=external) open item was recorded")

    linked = 0
    for item in external_items:
        if not item.converted_to:
            violations.append(f"{item.question!r}: no converted_to — not linked to a provisional assumption")
            continue
        assumption = entities_after.get(item.converted_to)
        if assumption is None or entity_type_for(item.converted_to) is not EntityType.ASSUMPTION:
            violations.append(f"{item.question!r}: converted_to {item.converted_to!r} is not a real Assumption")
            continue
        assert isinstance(assumption, Assumption)
        if not (assumption.provisional and assumption.user_confirmation_required):
            violations.append(f"{item.question!r}: linked assumption is not provisional+confirmation-required")
            continue
        linked += 1

    silent_assumptions = [
        eid for eid in new_assumptions
        if not entities_after[eid].provisional and not entities_after[eid].user_confirmation_required
    ]
    if silent_assumptions:
        violations.append("a silent assumption (neither provisional nor confirmation-required) was recorded")

    return ExternalInputReport(
        open_item_count=len(external_items),
        linked_to_provisional_assumption_count=linked,
        violations=violations,
    )
