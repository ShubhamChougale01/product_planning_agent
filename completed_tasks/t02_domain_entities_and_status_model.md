# T02 — Domain entities and the status model

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.7, §1.1, §1.15, S1.1–S1.2 |

## Prerequisites

- [x] **T01**

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

- [x] All seven entities round-trip to JSON and back unchanged
- [x] A bad enum value raises `ValidationError`
- [x] An empty `confidence_basis` raises — it is required, not optional
- [x] No field anywhere accepts a numeric confidence
- [x] `Unknown` has separate `blocking` and `route` — a blocking research item is representable
- [x] `CONFIRMED → PROPOSED` raises; `PROPOSED → CONFIRMED` passes
- [x] Every entity type has transition coverage in tests

## Traps

`Unknown.blocking` and `Unknown.route` must stay separate fields. Merging them back into one
enum makes "blocking **and** needs research" — a common case — unrepresentable, and breaks the
readiness gate rule in T10.

---

## Build record (completed 2026-09-23)

### A genuine gap in DESIGN.md §2.7, resolved by assumption, then confirmed by the user

§2.7 gives an explicit status enum for five of the seven entities (Requirement, Assumption,
Decision, Unknown, Risk) but **not for Question/Answer or ResearchFinding**, even though the
shared base line says every entity carries `status`. This is a real spec gap, not something I
should have inferred silently, so it was written up in `blockers.md` as decision #7 pending
confirmation.

**Confirmed 2026-09-23, with one change from the original assumption:** the user kept the enum
shape but replaced `SUPERSEDED` with `REPLACED` for both entities, to read more plainly as "a
newer answer/finding has taken its place." `models.py` and `transitions.py` were updated to match;
`SUPERSEDED` is unchanged for every other entity (Requirement, Assumption, Decision) — this rename
is scoped to these two only.

| Entity | Status enum (confirmed) | Reasoning |
|---|---|---|
| `QuestionAnswer` | `PENDING \| ANSWERED \| REPLACED` | Mirrors the record's own lifecycle: asked, then answered (any `answer_kind`), or replaced by a later round |
| `ResearchFinding` | `ACTIVE \| REPLACED` | `stale_after_days` already tracks *staleness by date*, computed elsewhere (T10-T12) — status only needs to track *replacement by a newer finding*, not implement its own staleness clock. Staleness and `REPLACED` are independent: a stale finding is not automatically `REPLACED`. |

### Other decisions taken, not in DESIGN.md verbatim

- **Same-status transitions (`frm == to`) are legal for every entity type.** Re-saving an entity
  without changing its status is not a status change, and the alternative would penalize
  idempotent writes for no reason (§1.15 names idempotency as a requirement elsewhere). Logged as
  decision #8 in `blockers.md`.
- **`extra="forbid"` on every entity.** A field outside the declared schema is a bug to catch at
  construction time. `Requirement.custom_fields` remains the one deliberate escape hatch
  (house-style extensibility, T04) — a typed dict, not an open top level.
- **ID shape is validated** (`REQ-nnn`, and `Q-nnn`/`ANS-nnn` for the shared record) even though
  the Done-when list doesn't ask for it. T07 owns actual ID *allocation*; this only catches a
  malformed ID being handed to the model at construction time, which is cheap insurance against a
  much harder bug later.

### What exists now

```
ppa/ledger/models.py        # EntityType, HistoryEntry, ConfidenceMixin, BaseEntity,
                             # Requirement, Assumption, Decision, Unknown, QuestionAnswer,
                             # ResearchFinding, Risk, ENTITY_TYPES registry
ppa/ledger/transitions.py   # TRANSITIONS matrix, IllegalTransition, validate_transition()
tests/test_ledger/test_models.py       # 61 tests
tests/test_ledger/test_transitions.py  # 39 tests
```

### Verification

```
$ pytest tests/test_ledger/   -> 100 passed
$ pytest                      -> 117 passed (T01's 16 + T02's 100 + 1 model-seam test added later)
```

No known bugs. No blockers encountered that stopped work — the status-enum gap above was worked
around with a documented, reversible assumption, then confirmed and closed (decision #7).

### Notes for whoever picks up T03

- `ppa/ledger/models.py` and `ppa/ledger/transitions.py` are the two files T03's event envelope
  will reference when it needs to know which entity types and statuses exist.
- `QuestionAnswer` and `ResearchFinding` use `REPLACED` as their terminal/superseding status, not
  `SUPERSEDED` — that's confirmed final (decision #7 in `blockers.md` §4), unlike every other
  entity which uses `SUPERSEDED`. Easy to typo across the two; `assert set(TRANSITIONS) ==
  set(EntityType)` at import time catches a missing entity type but not a wrong status name.

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
