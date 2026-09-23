# T10 — Coverage and readiness engines

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.2, §3.6, §6.1, §6.2, §6.5, S4.1, S4.3 |

## Prerequisites

- [ ] **T04**
- [ ] **T07**

## Why this task exists

The readiness gate is the stopping criterion — the single biggest hole in the original spec. It
is arithmetic, computed in Python, never a model judgment. Coverage is likewise **derived**: the
model moves the meter only by recording real entities, never by declaring progress.

## What to build

### Coverage engine — `ppa/engines/coverage.py`

`compute_coverage(ledger, profile) -> dict[area, CoverageState]`

State is **derived** from which entities cover which areas and at what confidence. Suggested rule:

- `UNTOUCHED` — no entity covers it
- `PARTIAL` — covered only by PROPOSED entities, or by assumptions alone
- `SUFFICIENT` — ≥1 CONFIRMED requirement covers it
- `CONFIRMED` — SUFFICIENT and the user explicitly confirmed the area in REVIEW

`progress(ledger, profile) -> (n_critical_sufficient, n_critical)`. Report against the **critical
set for the profile**, not all twelve — otherwise the number drifts as non-critical areas fill in.

**Nothing outside this engine may set an area's state.** There is deliberately no setter.

### Readiness gate — `ppa/engines/readiness.py`

`check_readiness(ledger, profile) -> (ready: bool, blockers: list[Blocker])`

Each `Blocker` names the entity and states what would clear it.

```
READY ⟺ all of:

1. every area critical FOR THIS PROFILE is SUFFICIENT or CONFIRMED

2. zero Unknowns with blocking == True and status == OPEN,
   EXCEPT owner_type == external, which convert to a provisional
   assumption and do not block                                    (§6.2)

   Stated in terms of `blocking`, not `route`. An unresearched item
   blocks only if it is itself blocking; a non-blocking RESEARCH item
   is an open item, not a gate failure.                            (§6.5)

3. every Assumption with impact == HIGH has status in {CONFIRMED, REJECTED}
   (a provisional assumption satisfies this only after the user
    acknowledges it in REVIEW)

4. every Decision with blocking == True has status == DECIDED
   (DECIDE_LATER permitted ONLY for blocking == False)

5. at least one Requirement covers each critical area

6. zero unresolved conflicts

7. the user has explicitly approved the REVIEW summary
```

`force_ready(reason)` — user override. Emits `user.forced_ready` listing everything skipped.

## Files touched

```
ppa/engines/coverage.py
ppa/engines/readiness.py
tests/test_engines/test_coverage.py
tests/test_engines/test_readiness.py
```

## Done when

- [ ] Progress is reproducible from the event log alone
- [ ] There is **no** public setter for coverage state — assert by inspection and by test
- [ ] The same ledger yields different progress for `engineer` vs `product` profiles
- [ ] Each of the seven gate conditions has a test that fails the gate **in isolation**
- [ ] Each failure produces a blocker naming the entity and what would clear it
- [ ] An external-owned blocking unknown does **not** block READY
- [ ] A non-blocking RESEARCH unknown does **not** block READY
- [ ] A blocking RESEARCH unknown **does** block READY

## Traps

Conditions 2 and 3 carry exceptions that exist precisely so client projects and
research-unavailable sessions do not stall. Implementing the gate without them will block every
real session — and the failure will look like a bug in the agent, not in the gate.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_engines/`
3. Commit: `git add -A && git commit -m "T10: Coverage and readiness engines"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t10_*.md completed_tasks\
   bash:     mv tasks/t10_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T10` on the board.
