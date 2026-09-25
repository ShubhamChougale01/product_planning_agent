# T09 — Digest projection

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.11, S3.1–S3.2 |

## Prerequisites

- [x] **T07**

## Why this task exists

The agent's view of state, bounded in size. By round five a real project has 40+ entities; the
raw ledger will not fit in context and would degrade attention if it did. Every prompt from T23
onward is written against the digest's shape, so it has to exist before any agent does.

## What to build

### Generator — `ppa/ledger/digest.py`

`generate_digest(project) -> str`, target **under 2k tokens** for a 50-entity ledger.

Contents, in this order:
1. Project name, seed requirement, current workflow state, round number
2. Coverage: each area with its state, critical ones marked, the critical fraction
3. **Every blocking item, in full** — never truncated, never summarized
4. **Every unconfirmed HIGH-impact assumption, in full**
5. Counts by entity type and status
6. Titles only for everything else
7. Open items due within 3 days

The asymmetry is the point: things that block are shown completely; everything else is a title
the agent can expand via a query.

### Freshness

Regeneration hooks to event append. A write followed immediately by a read must reflect the
write. Never serve a stale digest.

## Files touched

```
ppa/ledger/digest.py
tests/test_ledger/test_digest.py
```

## Done when

- [x] A 50-entity ledger digests to under 2k tokens
- [x] Zero blocking items are omitted or truncated, at any ledger size
- [x] Zero unconfirmed HIGH-impact assumptions are omitted
- [x] A write followed immediately by `read_digest` reflects that write
- [x] Digest generation for a 500-event project takes under 200ms

## Build record

Built `ppa/ledger/digest.py` — `generate_digest(project, entities, coverage=..., round_number=...,
now=...)` is the pure renderer; `read_digest(project, ...)` is the fresh-read convenience wrapper
S3.2 asks for. Coverage state is deliberately **not** computed here: T10 (`ppa/engines/coverage.py`)
does not exist yet and owns that exclusively ("nothing outside this engine may set an area's
state"), so `generate_digest` takes `coverage` as an already-computed mapping and defaults every
area to `UNTOUCHED` when none is supplied — T10 will be the first real caller to pass one in.
Blocking items (Unknown/Decision `blocking` fields) and unconfirmed HIGH assumptions are plain
filters over entity fields the digest can read directly, no engine dependency needed.

One real gap found and fixed in the same session, logged as decision #18: `read_digest` built on
T07's `rebuild_all` blew the 200ms budget (~460ms for 500 events) because `rebuild_all` rewrites
every entity file to disk on every call — correct for its own purpose, wrong cost for a read that
may happen many times per turn. Added `ppa/ledger/materialize.py::current_entities` (the same fold,
no file writes) and pointed `read_digest` at it; `rebuild_all`'s own behavior and tests are
untouched.

Tests: `tests/test_ledger/test_digest.py`, 9 new tests. Full suite re-run: **269 passed**
(260 after T08, +9).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/`
3. Commit: `git add -A && git commit -m "T09: Digest projection"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t09_*.md completed_tasks\
   bash:     mv tasks/t09_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T09` on the board.
