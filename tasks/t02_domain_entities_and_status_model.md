# T02 — Domain entities and the status model

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.7, §1.1, §1.15, S1.1–S1.2 |

## Prerequisites

- [ ] **T01**

## Why this task exists

The schema is the contract every later tool must satisfy. Writing it before any prompt means
the model is constrained by types rather than by polite instructions. Two things here were bugs
in an earlier draft and must not come back: numeric confidence, and a single `classification`
enum on Unknown.

## What to build

### Entities

Seven Pydantic models in `ppa/ledger/models.py`. Every one carries `id`, `version`, `status`,
`created_at`, `updated_at`, `created_by`, `updated_by`, `history: list[HistoryEntry]`.

**Requirement** `REQ-nnn` — `statement`, `type(functional|non_functional|constraint)`,
`status(PROPOSED|CONFIRMED|REJECTED|SUPERSEDED)`, `confidence`, `confidence_basis`,
`covers_areas[]`, `derived_from_answers[]`, `depends_on_assumptions[]`, `depends_on_decisions[]`,
`priority(must|should|could|wont_v1)`, `needs_user_confirmation`, `custom_fields{}`

**Assumption** `ASM-nnn` — `statement`, `reason`, `impact(HIGH|MEDIUM|LOW)`, `confidence`,
`confidence_basis`, `status(PROPOSED|CONFIRMED|REJECTED|SUPERSEDED)`, `affects_requirements[]`,
`affects_areas[]`, `user_confirmation_required`, `confirmed_at`, `confirmed_by`, `provisional`

**Decision** `DEC-nnn` — `question`, `status(OPEN|DECIDE_LATER|DECIDED|SUPERSEDED)`, `blocking`,
`owner`, `owner_type(user|external|agent)`, `identified_at`, `expected_decision_date`,
`decided_at`, `defer_reason`, `options[]`, `chosen_option`, `rationale`, `prerequisites[]`,
`current_assumption`, `related_requirements[]`, `related_research[]`

**Unknown** `UNK-nnn` — `question`, `area`, `why_it_matters`, **`blocking: bool`**,
**`route(GUIDANCE|RESEARCH|USER_DECISION|ASSUMPTION|OPTIONAL|FUTURE)`**, `owner_type`,
`status(OPEN|RESOLVED|CONVERTED)`, `converted_to`

**Question/Answer** `Q-nnn`/`ANS-nnn` — one record, two ID series. `text`, `why_asked`,
`target_areas[]`, `round`, `suggested_options[]`, `recommended_default`,
`answer_kind(answered|dont_know|decide_later|not_relevant)`, `dont_know_kind`, `answer_text`,
`answered_at`

**ResearchFinding** `RES-nnn` — `question`, `method`, `summary`, `options_found[]`, `sources[]`,
`confidence`, `confidence_basis`, `researched_at`, `stale_after_days` (default 90), `feeds_decision`

**Risk** `RSK-nnn` — `statement`, `likelihood`, `impact`, `area`, `mitigation`,
`status(OPEN|MITIGATED|ACCEPTED|CLOSED)`. Declared now, **not written in v1** — Planning owns it in v2.

### Confidence

`confidence: Literal["HIGH","MEDIUM","LOW"]` with a **required non-empty** `confidence_basis: str`.
No percentages anywhere. HIGH = user said it. MEDIUM = strongly implied. LOW = agent inferred.

### Status transitions

`ppa/ledger/transitions.py` — legal transitions as `dict[EntityType, dict[Status, set[Status]]]`,
plus `validate_transition(entity_type, frm, to) -> None | raises IllegalTransition`.

## Files touched

```
ppa/ledger/models.py
ppa/ledger/transitions.py
tests/test_ledger/test_models.py
tests/test_ledger/test_transitions.py
```

## Done when

- [ ] All seven entities round-trip to JSON and back unchanged
- [ ] A bad enum value raises `ValidationError`
- [ ] An empty `confidence_basis` raises — it is required, not optional
- [ ] No field anywhere accepts a numeric confidence
- [ ] `Unknown` has separate `blocking` and `route` — a blocking research item is representable
- [ ] `CONFIRMED → PROPOSED` raises; `PROPOSED → CONFIRMED` passes
- [ ] Every entity type has transition coverage in tests

## Traps

`Unknown.blocking` and `Unknown.route` must stay separate fields. Merging them back into one
enum makes "blocking **and** needs research" — a common case — unrepresentable, and breaks the
readiness gate rule in T10.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/`
3. Commit: `git add -A && git commit -m "T02: Domain entities and the status model"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t02_*.md completed_tasks\
   bash:     mv tasks/t02_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T02` on the board.
