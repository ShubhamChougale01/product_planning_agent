"""Conflict candidate detection — deterministic first pass only (DESIGN.md
§1.9, §1.10, §3.7, S4.6).

`find_conflict_candidates` never adjudicates whether two statements actually
contradict each other — that judgment call belongs to the model, later
(T30, Review mode). This module only finds *pairs worth a model call*, using
signals cheap enough to run on every new answer with zero LLM cost:

- shared coverage areas
- shared entity references (both texts name the same ledger id)
- negation markers paired with a shared keyword
- a curated list of mutually exclusive terms
- a large disparity between numbers mentioned in each text

**Tuning target: recall over precision.** A missed conflict silently
corrupts the ledger; a false candidate costs one cheap model call in T30.
Every signal function below is deliberately permissive for exactly that
reason — don't tighten one without re-reading this paragraph first.
"""

from __future__ import annotations

import re
from typing import Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict

from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType, QuestionAnswer

Signal = Literal[
    "shared_area",
    "shared_entity_reference",
    "negation",
    "mutually_exclusive_terms",
    "quantity_contradiction",
]


class Candidate(BaseModel):
    """A pair worth a human or a model looking at — never a verdict."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str
    candidate_id: str
    signals: list[Signal]
    description: str


_NEGATION_MARKERS = {
    "not", "no", "never", "cannot", "can't", "won't", "isn't", "doesn't", "without",
}

_MUTUALLY_EXCLUSIVE_TERMS: list[tuple[str, str]] = [
    ("internal tool", "public launch"),
    ("internal", "public"),
    ("on-prem", "cloud"),
    ("on-premise", "cloud"),
    ("phased rollout", "big bang"),
    ("opt-in", "mandatory"),
    ("free", "paid"),
    ("synchronous", "asynchronous"),
    ("online", "offline"),
    ("read-only", "read-write"),
]
"""Deliberately small and curated, not learned — each pair is a plain-English
antonym pair likely to show up in a requirements conversation. Widen this
list as real conflicts are found; guessing more pairs speculatively risks
false positives with no test backing them."""

_ENTITY_REF_PATTERN = re.compile(r"\b[A-Z]{2,4}-\d{3,}\b")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
_WORD_PATTERN = re.compile(r"[a-z']+")

_QUANTITY_CONTRADICTION_RATIO = 10.0
"""Two numbers are only flagged if one is at least this many times the
other — "20 users" vs "20,000 users" is worth a look; "20 users" vs "22
users" almost certainly is not."""


def _shared_areas(areas_a: Iterable[str], areas_b: Iterable[str]) -> bool:
    return bool(set(areas_a) & set(areas_b))


def _shared_entity_references(text_a: str, text_b: str) -> bool:
    return bool(set(_ENTITY_REF_PATTERN.findall(text_a)) & set(_ENTITY_REF_PATTERN.findall(text_b)))


def _has_negation_conflict(text_a: str, text_b: str) -> bool:
    words_a = set(_WORD_PATTERN.findall(text_a.lower()))
    words_b = set(_WORD_PATTERN.findall(text_b.lower()))
    shared_content_words = (words_a & words_b) - _NEGATION_MARKERS
    if not shared_content_words:
        return False
    a_negated = bool(words_a & _NEGATION_MARKERS)
    b_negated = bool(words_b & _NEGATION_MARKERS)
    return a_negated != b_negated


def _has_mutually_exclusive_terms(text_a: str, text_b: str) -> bool:
    lower_a, lower_b = text_a.lower(), text_b.lower()
    for term_x, term_y in _MUTUALLY_EXCLUSIVE_TERMS:
        if (term_x in lower_a and term_y in lower_b) or (term_y in lower_a and term_x in lower_b):
            return True
    return False


def _has_quantity_contradiction(text_a: str, text_b: str) -> bool:
    numbers_a = [float(n.replace(",", "")) for n in _NUMBER_PATTERN.findall(text_a)]
    numbers_b = [float(n.replace(",", "")) for n in _NUMBER_PATTERN.findall(text_b)]
    for a in numbers_a:
        if a == 0:
            continue
        for b in numbers_b:
            if b == 0:
                continue
            if max(a, b) / min(a, b) >= _QUANTITY_CONTRADICTION_RATIO:
                return True
    return False


def _entity_text(entity: BaseEntity) -> str:
    return (
        getattr(entity, "statement", None)
        or getattr(entity, "answer_text", None)
        or getattr(entity, "question", None)
        or getattr(entity, "text", None)
        or getattr(entity, "summary", None)
        or ""
    )


def _entity_areas(entity: BaseEntity) -> list[str]:
    return list(
        getattr(entity, "covers_areas", None)
        or getattr(entity, "affects_areas", None)
        or getattr(entity, "target_areas", None)
        or []
    )


_COMPARABLE_TYPES = (EntityType.REQUIREMENT, EntityType.ASSUMPTION)
"""DESIGN.md §1.10/§3.7: "does the new answer contradict any CONFIRMED
requirement or assumption?" — candidate detection is scoped to these two
entity types, and only once they've reached their own `CONFIRMED` status.
A PROPOSED requirement isn't settled enough yet to be worth flagging a
conflict against; that would just be normal refinement, not contradiction."""


def find_conflict_candidates(
    new_answer: QuestionAnswer,
    ledger: Mapping[str, BaseEntity],
) -> list[Candidate]:
    """Compare `new_answer` against every `CONFIRMED` Requirement or
    Assumption in `ledger` (§3.7 step 1 — everything else is either not yet
    settled enough to contradict, or not a type this signal set applies to),
    and return one `Candidate` per entity that trips at least one signal.
    Order matches `ledger`'s own iteration order."""

    subject_text = new_answer.answer_text or new_answer.text
    subject_areas = new_answer.target_areas

    candidates: list[Candidate] = []
    for entity_id, entity in ledger.items():
        if entity_id == new_answer.id:
            continue
        if entity_type_for(entity_id) not in _COMPARABLE_TYPES:
            continue
        if entity.status != "CONFIRMED":
            continue

        other_text = _entity_text(entity)
        if not other_text:
            continue

        signals: list[Signal] = []
        if _shared_areas(subject_areas, _entity_areas(entity)):
            signals.append("shared_area")
        if _shared_entity_references(subject_text, other_text):
            signals.append("shared_entity_reference")
        if _has_negation_conflict(subject_text, other_text):
            signals.append("negation")
        if _has_mutually_exclusive_terms(subject_text, other_text):
            signals.append("mutually_exclusive_terms")
        if _has_quantity_contradiction(subject_text, other_text):
            signals.append("quantity_contradiction")

        if signals:
            candidates.append(
                Candidate(
                    subject_id=new_answer.id,
                    candidate_id=entity_id,
                    signals=signals,
                    description=f"{new_answer.id} vs {entity_id}: {', '.join(signals)}",
                )
            )

    return candidates
