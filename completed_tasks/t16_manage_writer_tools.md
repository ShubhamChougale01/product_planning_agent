# T16 — The manage_* writers

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.9, §2.8, §2.13, S5.5 |

## Prerequisites

- [x] **T15**

## Why this task exists

Four parameterized writers rather than twenty CRUD tools. They stay separate from each other —
merging them into one `manage_entity` would hit a tool-count target while moving the same
selection problem inside the tool, against a description covering four different schemas.

The load-bearing requirement: **provenance links are mandatory**. Without them, T11's impact
graph has no edges and impact analysis degrades into LLM guesswork.

## What to build

### Four tools

```
manage_requirement(operation, ...)   create | revise | confirm | reject | supersede
manage_assumption(operation, ...)    create | confirm | reject | modify | supersede
manage_decision(operation, ...)      open   | defer   | decide | supersede
manage_unknown(operation, ...)       record | classify | resolve | convert
```

### Every write runs this sequence

1. **Permission** (T14)
2. **Schema** — Pydantic, entity model from T02
3. **Workflow** — is this operation legal in the current state?
4. **Semantic** — e.g. a Requirement cannot be CONFIRMED while a blocking Unknown covering the
   same area is OPEN
5. **Consistency** — version match, referenced IDs exist, transition legal (T02)
6. Secret-scan free text (T06) → append event → materialize → regenerate digest → audit

### Mandatory provenance

`manage_requirement(create)` **must** receive `covers_areas` and at least one of
`derived_from_answers`, `depends_on_assumptions`, `depends_on_decisions`. Reject otherwise.

`manage_decision(defer)` requires `defer_reason`, `owner`, `owner_type` and an
`expected_decision_date` computed by T12's rule.

`manage_unknown(record)` requires both `blocking` and `route`.

### Error messages must be actionable

A rejection has to tell the model exactly what to fix. `"validation failed"` causes retry loops.

> `VALIDATION: manage_requirement(create) requires covers_areas (non-empty list of area keys from
> config/areas.py). Received: []. Valid keys: problem, users, jobs, …`

## Files touched

```
ppa/tools/discovery_tools.py  (extend)
tests/test_tools/test_writers.py
tests/test_validation/test_semantic.py
```

## Done when

- [x] A requirement with no `covers_areas` is rejected with a message specific enough to fix on retry
- [x] A requirement with no provenance link at all is rejected
- [x] `manage_unknown(record)` without both `blocking` and `route` is rejected
- [x] `manage_decision(defer)` without `defer_reason`, `owner` or `owner_type` is rejected —
      **corrected wording, see decision #24 in `blockers.md`.** `expected_decision_date` is never
      caller-supplied; it is always computed by the tool itself from T12's rule
      (`ppa.engines.dates.expected_decision_date`) against the decision's own `blocking`/`affects`
      fields, matching decision #21's `expected_decision_date(decision, now)` signature. A field
      that the tool always computes can never be "missing" on the success path, so the original
      wording was untestable as written.
- [x] Confirming a requirement whose area has an open blocking unknown is rejected as semantic
- [x] Every write emits exactly one event and one audit record
- [x] Every write is idempotent under a repeated `idem_key`
- [x] Free text passes through secret scanning before the event is built

## Traps

Resist adding a fifth `manage_*` for research — `manage_research` belongs to the Guidance and
Research subagents (T14 grants), not to Discovery. Findings should be written by the agent that
did the work.

## Build record

Extended `ppa/tools/discovery_tools.py` with all four `manage_*` writers. `_generic_transition` is
the one function every non-`create`/`open`/`record` operation across all four entity types goes
through (revise/confirm/reject/supersede for Requirement; confirm/reject/modify/supersede for
Assumption; defer/decide/supersede for Decision; classify/resolve/convert for Unknown), configured
per operation by a small `_OpConfig` row (event type, target status, required fields, updatable
fields, which fields get secret-scanned, which source statuses the operation is legal from). `create`/
`open`/`record` are their own functions since they build a brand-new entity dict rather than mutate
one. Each of the four public `manage_*` functions is a thin dispatcher: `create`/`open`/`record` goes
to its own builder, every other operation goes through `_generic_transition` with that entity type's
op table.

**Audit is self-recorded inside each writer**, not left to `ppa/tools/dispatch.py` — that dispatcher
still wraps every handler call as `success=True` unconditionally (its own docstring says T19 fixes
this), so it cannot be trusted yet to audit a rejected write correctly. Logged as decision #24 in
`blockers.md` for T19 to reconcile when it wires the five validation layers centrally.

Semantic layer 4 (the one rule this build needs — a Requirement cannot be `CONFIRMED` while a
blocking `Unknown` covering the same area is still `OPEN`) lives as
`_requirement_confirm_semantic_check` in `discovery_tools.py`, tested directly in
`tests/test_validation/test_semantic.py` as well as end-to-end in `tests/test_tools/test_writers.py`.
`ppa/validation/semantic.py` stays the T19 stub — moving this rule there is part of that task's own
"make it explicit, uniform and observable" scope, not a T16 concern.

**Corrected one Done-when box while building it** (decision #24, `blockers.md`): "`manage_decision
(defer)` without `expected_decision_date` is rejected" cannot be tested as written once
`expected_decision_date` is always computed by the tool (per decision #21's `expected_decision_date
(decision, now)` signature) rather than caller-supplied — a value the tool always produces can never
be "missing" on a success path. Reworded to name the fields a caller actually supplies
(`defer_reason`, `owner`, `owner_type`), and added a dedicated test confirming the computed date
matches T12's rule exactly (`+3d` blocking+architecture, in `test_decision_defer_computes_expected_
decision_date_via_t12_rule`).

Tests: `tests/test_tools/test_writers.py` (33 tests) + `tests/test_validation/test_semantic.py`
(7 tests) = 37 new tests. Full suite re-run: **556 passed** (519 baseline + 37).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_tools/`
3. Commit: `git add -A && git commit -m "T16: The manage_* writers"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t16_*.md completed_tasks\
   bash:     mv tasks/t16_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T16` on the board.
