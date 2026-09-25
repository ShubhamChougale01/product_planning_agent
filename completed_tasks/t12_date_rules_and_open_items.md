# T12 — Date rules and open items

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.12, §1.13, §3.8, S4.4–S4.5 |

## Prerequisites

- [x] **T07**

## Why this task exists

The model does not reliably know today's date and will confabulate it, so all date arithmetic is
Python. "Expected decision date" needs a stated rule rather than a guess — a date the user did
not set and cannot explain is noise.

## What to build

### Dates — `ppa/engines/dates.py`

**Every function takes `now` as a parameter.** Never call `datetime.now()` inside the engine —
that is what makes these testable with a frozen clock.

`expected_decision_date(decision, now)` — v1 tier rule, stated openly to the user and overridable:

```
blocking + affects architecture  → now + 3 days
blocking + affects scope         → now + 5 days
non-blocking                     → now + 14 days, or null with "before build starts"
```

Also `is_overdue(item, now)`, `due_within(items, days, now)`.

### Open items — `ppa/engines/open_items.py`

Collect and sort by due date then severity:
- blocking Unknowns still OPEN
- Decisions with status OPEN or DECIDE_LATER
- unconfirmed HIGH-impact Assumptions
- queued RESEARCH_REQUIRED items
- items whose expected decision date is approaching or passed

Each carries owner, `owner_type`, due date, blocking flag, and what would resolve it.
Output shape must match the status board in DESIGN.md §3.8.

## Files touched

```
ppa/engines/dates.py
ppa/engines/open_items.py
tests/test_engines/test_dates.py
tests/test_engines/test_open_items.py
```

## Done when

- [x] All date tests pass with a frozen clock (`freezegun`)
- [x] No engine function calls `datetime.now()` internally — grep and assert
- [x] The tier rule is stated in one readable place and is overridable
- [x] Open items output matches the §3.8 board layout from fixture data
- [x] Externally-owned items are visibly distinguished from user-owned ones
- [x] Overdue items sort above merely-due ones

## Build record

Built `ppa/engines/dates.py` (`expected_decision_date`, `is_overdue`, `due_within`,
`EXPECTED_DECISION_DATE_RULE`) and `ppa/engines/open_items.py` (`OpenItem`, `collect_open_items`).

`expected_decision_date` takes `affects` as an explicit argument rather than deriving it from a
`Decision` object, since `Decision` carries no field that says whether it affects architecture or
scope — logged as decision #21, flagged for confirmation the same way decision #19's readiness-gate
parameters were. Also refactored `ppa/ledger/digest.py`'s T09-era "Due within 3 days" section to call
this task's own `collect_open_items`/`due_within` instead of its original hand-rolled, Decision-only
filter, so date-window logic lives in exactly one place.

A first attempt at the DESIGN.md research for this task went to a forked subagent that violated its
explicit read-only briefing twice — wrote files directly and drifted to researching an unrelated
future task. Killed both times; its written `dates.py`/`test_dates.py` were reviewed line by line,
not trusted blindly, and rewritten in full before being kept (the `affects`-as-parameter design it
landed on independently matched my own reasoning once verified against DESIGN.md §1.13 directly, so
that specific choice survived review — nothing else did).

Tests: `tests/test_engines/test_dates.py` (14), `tests/test_engines/test_open_items.py` (7).
Full suite re-run: **326 passed** (305 after T11, +21).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_engines/`
3. Commit: `git add -A && git commit -m "T12: Date rules and open items"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t12_*.md completed_tasks\
   bash:     mv tasks/t12_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T12` on the board.
