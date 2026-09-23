# T07 — Materializer, ID allocation, idempotency

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.14, S2.2–S2.4 |

## Prerequisites

- [ ] **T06**

## Why this task exists

Entity JSON files are a *view* of the event log, not a second source of truth. Rebuilding them
from events is what makes the ledger recoverable and makes transactions work without an undo
mechanism. IDs and idempotency live here because both need the same lock as the append.

## What to build

### Materializer

`materialize(entity_id)` folds events into current state; `rebuild_all()` regenerates every
entity file from `events.ndjson`.

**A transaction without a `txn.commit` is ignored entirely.** Events carrying an uncommitted
`txn_id` contribute nothing to materialized state. This is the rollback mechanism.

### ID allocation

Counters in `project.json`, allocated **under the same lock as the append** so an ID can never
be handed out twice or orphaned. `REQ-001`, `ASM-001`, … Never model-generated.

### Idempotency

Every write accepts an `idem_key`. A replayed key returns the original result without appending
a second event. Keep a key→event_id map in `project.json`.

## Files touched

```
ppa/ledger/store.py  (extend)
ppa/ledger/materialize.py
tests/test_ledger/test_materialize.py
tests/test_ledger/test_idempotency.py
```

## Done when

- [ ] Deleting every entity file and running `rebuild_all()` reproduces them byte-identically
- [ ] An aborted transaction leaves no trace in materialized state
- [ ] Parallel allocation of 100 IDs yields 100 distinct sequential IDs
- [ ] The same write called three times produces one entity and one event
- [ ] Rebuilding a 500-event log completes in under a second

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/`
3. Commit: `git add -A && git commit -m "T07: Materializer, ID allocation, idempotency"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t07_*.md completed_tasks\
   bash:     mv tasks/t07_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T07` on the board.
