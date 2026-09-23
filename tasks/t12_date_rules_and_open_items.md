# T12 — Date rules and open items

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.12, §1.13, §3.8, S4.4–S4.5 |

## Prerequisites

- [ ] **T07**

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

- [ ] All date tests pass with a frozen clock (`freezegun`)
- [ ] No engine function calls `datetime.now()` internally — grep and assert
- [ ] The tier rule is stated in one readable place and is overridable
- [ ] Open items output matches the §3.8 board layout from fixture data
- [ ] Externally-owned items are visibly distinguished from user-owned ones
- [ ] Overdue items sort above merely-due ones

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
