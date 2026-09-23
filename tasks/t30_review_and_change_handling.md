# T30 — Review mode and change handling

| | |
|---|---|
| **Phase** | E · Product surface |
| **Estimate** | 1 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.10, §3.7, S10.1–S10.2 |

## Prerequisites

- [ ] **T27**
- [ ] **T29**

## Why this task exists

Two things that make the ledger trustworthy over time: assumptions get explicitly confirmed
before READY, and a user contradicting themselves in round 4 does not silently corrupt what they
said in round 1.

## What to build

### Review mode

Walk **HIGH-impact unconfirmed assumptions one at a time**: confirm / reject / modify. Present
open items, provisional external assumptions, and any unresolved conflicts. Then request explicit
approval.

READY is unreachable without an explicit user approval event in the log (gate condition 7).

### Change handling

`CHANGE_REQUESTED` is reachable from every workflow state — a user saying "oh, also mobile"
during REVIEW must not be lost.

```
1 detect      conflict candidates from T11 (deterministic)
2 adjudicate  model decides: real contradiction, refinement, or unrelated?
3 surface     show both versions with dates, offer supersede or branch
4 supersede   new entity version with change_reason; old marked SUPERSEDED
5 impact      analyze_impact -> report affected entities
6 recompute   readiness gate; rewind workflow state to the earliest affected
```

### Surfacing a conflict

> This changes something we'd settled. REQ-002 says *internal tool, ~20 users* — you confirmed
> that on Sep 21. Public launch contradicts it. Should I supersede REQ-002, or are these two
> different phases?

## Files touched

```
ppa/agents/modes/review.py
ppa/agents/modes/change.py
tests/eval/test_review.py
tests/eval/test_change.py
```

## Done when

- [ ] READY is unreachable without an explicit user approval event
- [ ] Every HIGH-impact assumption is walked individually, never batched into one prompt
- [ ] \"We also need a mobile app\" after READY produces a new requirement version
- [ ] The change produces an impact report naming affected entities
- [ ] The gate drops back to NOT READY and the workflow rewinds to the earliest affected state
- [ ] The `contradicts_self` persona's conflict is surfaced, not silently appended
- [ ] Superseded entities keep their history and are marked SUPERSEDED, never deleted

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T30: Review mode and change handling"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t30_*.md completed_tasks\
   bash:     mv tasks/t30_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T30` on the board.
