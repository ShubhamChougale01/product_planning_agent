"""Legal status transitions, as data (DESIGN.md §1.15, §2.7, S1.2).

The matrix lives here, not scattered across tool handlers, so the whole set of
legal moves is auditable in one place and every entity type is forced to
declare one — a status field with no matrix entry is a bug, not a silent
allow-everything default.
"""

from __future__ import annotations

from ppa.ledger.models import EntityType


class IllegalTransition(Exception):
    """Raised when `frm -> to` is not in `TRANSITIONS` for `entity_type`."""

    def __init__(self, entity_type: EntityType, frm: str, to: str) -> None:
        self.entity_type = entity_type
        self.frm = frm
        self.to = to
        super().__init__(f"{entity_type.value}: {frm!r} -> {to!r} is not a legal transition")


# dict[EntityType, dict[from_status, set[legal_to_status]]]
#
# A status with an empty set is terminal for that entity type. Reconsidering a
# terminal entity means creating a *new* one that supersedes it, not resurrecting
# the old one — REJECTED and CLOSED do not transition back to an open state.
TRANSITIONS: dict[EntityType, dict[str, set[str]]] = {
    EntityType.REQUIREMENT: {
        "PROPOSED": {"CONFIRMED", "REJECTED", "SUPERSEDED"},
        "CONFIRMED": {"SUPERSEDED"},
        "REJECTED": set(),
        "SUPERSEDED": set(),
    },
    EntityType.ASSUMPTION: {
        "PROPOSED": {"CONFIRMED", "REJECTED", "SUPERSEDED"},
        "CONFIRMED": {"SUPERSEDED"},
        "REJECTED": set(),
        "SUPERSEDED": set(),
    },
    EntityType.DECISION: {
        "OPEN": {"DECIDE_LATER", "DECIDED", "SUPERSEDED"},
        "DECIDE_LATER": {"OPEN", "DECIDED", "SUPERSEDED"},
        "DECIDED": {"SUPERSEDED"},
        "SUPERSEDED": set(),
    },
    EntityType.UNKNOWN: {
        "OPEN": {"RESOLVED", "CONVERTED"},
        "RESOLVED": set(),
        "CONVERTED": set(),
    },
    EntityType.QUESTION_ANSWER: {
        "PENDING": {"ANSWERED", "REPLACED"},
        "ANSWERED": {"REPLACED"},
        "REPLACED": set(),
    },
    EntityType.RESEARCH_FINDING: {
        "ACTIVE": {"REPLACED"},
        "REPLACED": set(),
    },
    EntityType.RISK: {
        "OPEN": {"MITIGATED", "ACCEPTED", "CLOSED"},
        "MITIGATED": {"CLOSED"},
        "ACCEPTED": {"CLOSED"},
        "CLOSED": set(),
    },
}

assert set(TRANSITIONS) == set(EntityType), (
    "Every EntityType must have a transition table, even if some rows are "
    "terminal-only — an entity type missing here would fall through to "
    "IllegalTransition's KeyError branch for every transition, silently."
)


def validate_transition(entity_type: EntityType, frm: str, to: str) -> None:
    """Raise `IllegalTransition` unless `frm -> to` is legal for `entity_type`.

    `frm == to` is always legal: saving an entity again without changing its
    status is not a status change, and treating it as an illegal transition
    would penalize idempotent writes (§1.15) for no reason.
    """
    if frm == to:
        return
    try:
        legal = TRANSITIONS[entity_type][frm]
    except KeyError as exc:
        raise IllegalTransition(entity_type, frm, to) from exc
    if to not in legal:
        raise IllegalTransition(entity_type, frm, to)
