# T31 — CLI and status board

| | |
|---|---|
| **Phase** | E · Product surface |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §3.8, §1.15, S10.3–S10.4 |

## Prerequisites

- [ ] **T30**

## Why this task exists

The interface for v1. The status board is rendered **purely from engine output** — the model
contributes nothing to it, which is what makes the numbers trustworthy.

## What to build

### Commands

```
ppa new <name>            create project, capture seed requirement and user profile
ppa chat <project>        the main loop
ppa status <project>      ONE surface: progress AND open items (§1.15).
                          --items filters to just the list
ppa history <entity-id>   version trail
ppa why <entity-id>       full provenance: what changed, when, why,
                          by which agent, under which tool, in which state
ppa client-questions      the external questionnaire (T27)
ppa force-ready           override the gate; records everything skipped
```

`status` and `items` are **one command**, not two concepts.

### Status board — `ppa/render/status_board.py`

```
PLANNING STATUS — Invoice Tracker            Session 3 · 2026-09-21 14:32

Coverage  6/7 critical ██████████░░   all areas 8/12   Round 3 · CLARIFY

  critical  ✓ problem ✓ users ✓ jobs ✓ scope_in ✓ success ✓ constraints
            ◐ scope_out (PARTIAL)
  other     ✓ existing_system ✓ platform   ○ data ○ nfr ○ rollout

Ledger
  Requirements   14   (11 confirmed · 3 proposed)
  Assumptions     5   (2 confirmed · 3 awaiting review ⚠ 1 HIGH impact)
  Decisions       4   (1 decided · 2 decide-later · 1 open 🔴 blocking)
  Unknowns        3   (1 blocking · 2 research)

Readiness   NOT READY — 3 blockers
  🔴 DEC-002  Auth approach undecided (blocking)      owner: you    due Sep 24
  🔴 UNK-007  Compliance scope unknown (blocking)     owner: you    due Sep 22
  ⚠  ASM-003  "Web only for v1" — HIGH impact, unconfirmed

Open items due within 3 days: 2      Overdue: 0
```

Report critical coverage as the headline fraction, with total areas secondary.

## Files touched

```
ppa/cli.py
ppa/render/status_board.py
ppa/render/question_card.py  (full)
tests/test_render/
```

## Done when

- [ ] A full clarification session runs end-to-end in the terminal
- [ ] The status board matches the layout above from fixture data
- [ ] The model contributes nothing to the board — it is pure engine output
- [ ] `status` shows progress and open items in one surface; `--items` filters
- [ ] `why <id>` reports agent, tool and workflow state, not just what changed
- [ ] Externally-owned items are visually distinct from user-owned ones
- [ ] The board renders correctly in a narrow (80-col) terminal

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_render/`
3. Commit: `git add -A && git commit -m "T31: CLI and status board"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t31_*.md completed_tasks\
   bash:     mv tasks/t31_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T31` on the board.
