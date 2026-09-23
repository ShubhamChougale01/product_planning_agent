# T16 — The manage_* writers

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.9, §2.8, §2.13, S5.5 |

## Prerequisites

- [ ] **T15**

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

- [ ] A requirement with no `covers_areas` is rejected with a message specific enough to fix on retry
- [ ] A requirement with no provenance link at all is rejected
- [ ] `manage_unknown(record)` without both `blocking` and `route` is rejected
- [ ] `manage_decision(defer)` without `expected_decision_date` is rejected
- [ ] Confirming a requirement whose area has an open blocking unknown is rejected as semantic
- [ ] Every write emits exactly one event and one audit record
- [ ] Every write is idempotent under a repeated `idem_key`
- [ ] Free text passes through secret scanning before the event is built

## Traps

Resist adding a fifth `manage_*` for research — `manage_research` belongs to the Guidance and
Research subagents (T14 grants), not to Discovery. Findings should be written by the agent that
did the work.

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
