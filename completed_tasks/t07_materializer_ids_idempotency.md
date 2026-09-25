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

- [x] Deleting every entity file and running `rebuild_all()` reproduces them byte-identically
- [x] An aborted transaction leaves no trace in materialized state
- [x] Parallel allocation of 100 IDs yields 100 distinct sequential IDs
- [x] The same write called three times produces one entity and one event
- [x] Rebuilding a 500-event log completes in under a second

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

---

## Build record (completed 2026-09-25)

### Entity file location — a gap DESIGN.md's §2.6 diagram leaves as "…"

§2.6's repository layout shows `projects/<slug>/.planning/` holding `events.ndjson`, `audit.ndjson`
and `…` — no filename or directory convention for the materialized entity views §1.8 calls "what
git diffs show and what humans read." Filled by assumption, same posture as decision #11: one flat
`entities/<entity_id>.json` per entity (a sibling of `events.ndjson`), keyed directly on the
globally-unique `entity_id` rather than nested by type — simplest structure that still makes every
entity's own git history a one-file diff. Logged in `blockers.md` as decision #14 for confirmation.

### `append_event`'s existing signature was not touched

T06's `append_event(fields, path) -> str` is already committed, tested and used by every T06 test.
Rather than widen its return type (which would have broken every `assert event_id == "EVT-..."` in
`test_append.py`), its internals were split into a lock-free `_append_locked()` core that both the
untouched `append_event()` and the new `append_event_with_id()` call — the old function is
byte-for-byte behaviorally identical, just refactored underneath.

### Why id allocation and idempotency are one combined function, not two independent ones

`allocate_id()` alone is safe against **collisions** (two callers can never get the same id) but
not against **orphaning** (a crash between allocating an id and appending the event that was meant
to use it still burns that id). The task's own wording — "never handed out twice **or orphaned**"
— asks for both. `append_event_with_id()` closes the orphaning gap by allocating and appending
inside one lock acquisition, and by checking `idem_key` *before* allocating — so a replayed write
never burns an id it will immediately discard. `allocate_id()` still exists standalone because the
task names "ID allocation" as its own sub-heading with its own Done-when box, and future callers
that only need an id (no paired event, e.g. a caller building a multi-entity transaction that
allocates several ids up front) shouldn't have to fake one through the combined function.

### Injecting the freshly allocated id into `after`

A real "create" event's `after` snapshot must contain the entity's own `id` field, but that id
isn't known until it's allocated *inside* the same lock the write needs. Rather than adding a
callback parameter, `append_event_with_id` just patches `fields["after"]["id"]` (when `after` is a
dict) to the freshly allocated `entity_id` after allocating and before constructing the `Event` —
the caller passes a template `after` dict with a placeholder id, no callback machinery needed.

### What exists now

```
ppa/ledger/store.py                     # allocate_id(), append_event_with_id(), WriteResult,
                                         # project.json read/write helpers (extends T06's module)
ppa/ledger/materialize.py                # materialize(), rebuild_all(), entity_type_for()
tests/test_ledger/test_materialize.py    # 10 tests
tests/test_ledger/test_idempotency.py    # 9 tests
```

### Verification

```
$ .venv/Scripts/python.exe -m pytest tests/test_ledger/test_materialize.py tests/test_ledger/test_idempotency.py -> 19 passed
$ .venv/Scripts/python.exe -m pytest                                                                              -> 246 passed
```

### Notes for whoever picks up T08

- `entities/` (flat, `<entity_id>.json`) is only an assumption pending confirmation (decision #14)
  — if overridden, `materialize.py`'s `_entity_file_path`/`rebuild_all` are the only places that
  need to change.
- `project.json` currently holds only `id_counters` and `idempotency` — T08 owns the rest of its
  shape (project name, profile, workflow_state, `ledger_version`, etc.). Read/write it through
  `ppa/ledger/store.py`'s `_read_project_meta`/`_write_project_meta` (or widen them) rather than a
  second, competing project.json writer.
- Real write tools (T13+) should call `append_event_with_id()`, not compose `allocate_id()` +
  `append_event()` themselves — that composition is exactly the orphaning gap this task closed.
