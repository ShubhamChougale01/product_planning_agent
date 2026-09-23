# T09 — Digest projection

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.11, S3.1–S3.2 |

## Prerequisites

- [ ] **T07**

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

- [ ] A 50-entity ledger digests to under 2k tokens
- [ ] Zero blocking items are omitted or truncated, at any ledger size
- [ ] Zero unconfirmed HIGH-impact assumptions are omitted
- [ ] A write followed immediately by `read_digest` reflects that write
- [ ] Digest generation for a 500-event project takes under 200ms

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
