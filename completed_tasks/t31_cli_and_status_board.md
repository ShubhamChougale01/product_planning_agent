# T31 — CLI and status board

| | |
|---|---|
| **Phase** | E · Product surface |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §3.8, §1.15, S10.3–S10.4 |

## Prerequisites

- [x] **T30**

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

- [x] A full clarification session runs end-to-end in the terminal
- [x] The status board matches the layout above from fixture data
- [x] The model contributes nothing to the board — it is pure engine output
- [x] `status` shows progress and open items in one surface; `--items` filters
- [x] `why <id>` reports agent, tool and workflow state, not just what changed
- [x] Externally-owned items are visually distinct from user-owned ones
- [x] The board renders correctly in a narrow (80-col) terminal

## Build record

`ppa/render/status_board.py` (new) — draws the whole board straight from engines already proven
elsewhere (`ppa/engines/coverage.py`, `readiness.py`, `open_items.py`, `dates.py`), plus two small
event-log folds it owns directly: which session this is and how many outer-loop rounds have run
(`_session_and_round_counts`, reusing T21's own `rounds_from_events` rather than a second round
counter), and which `DiscoveryMode` the project is currently in (reads the same `discovery_mode`
project-meta key `ppa.agents.turn` already writes). `gate_inputs` assembles `check_readiness`'s
three T30-owned inputs (`review_approved`, `confirmed_areas`, `unresolved_conflicts`) from
`ppa.agents.modes.review.readiness_gate_inputs` / `ppa.agents.modes.change.
unresolved_conflicts_from_events` — the first real caller to wire all three together for display.
`render_open_items` is the `--items` view: the same "Readiness" section plus the full open-items
list, never a second computation. `render_history`/`render_provenance` back `ppa history`/`ppa why`
— provenance folds `audit.ndjson` records whose `inputs_ref.entity_id` matches, reporting agent,
tool, operation and workflow state per record. Every title is truncated to 24 characters
(`_truncate`) so even the worst-case blocker line (icon + entity id + title + owner + due) still
fits an 80-column terminal — real entity titles are short, human-authored one-liners by this
codebase's own convention, but the truncation makes the guarantee unconditional rather than resting
on that convention holding.

`ppa/render/question_card.py` (full) — `parse_answer` turns free text typed at `ppa chat`'s prompt
into one of the four answer affordances: a whole-phrase match for `dont_know`/`decide_later` (never
a substring match, so a real answer containing the word "later" is not misread), an explicit
`not relevant: <reason>` prefix, everything else recorded as `answered` verbatim.

`ppa/tools/interaction.py::answer_pending_question` (new function; not in this task's own "Files
touched" list — see decision #39) — records an answer against a `Q-nnn` a prior turn already asked
and left `PENDING`, the "caller answers it later" half `ask_user`'s own docstring names as this
task's job. Mirrors `_ask_and_maybe_answer_one`'s replace-then-answer event pair exactly; no
existing function's behavior changed.

`ppa/cli.py` — `chat` runs `ppa.orchestrator.loop.run_turn` in a loop, rendering and collecting an
answer for every `PENDING` question a `SUSPENDED` turn leaves, until the session completes,
escalates, or reports `NOT_IMPLEMENTED`; `status` gained `--items`; `history`/`force-ready` are new;
`why` now also prints `render_provenance`. `plan` (T21's stub) is removed — `chat` takes its place,
per this task's own "Commands" section. `report` stays a stub (see decision #39).

**Decision #39** (`blockers.md`): six related judgment calls, including the `answer_pending_question`
addition, proving `ppa chat` without a model (the same `_FixtureAgent` pattern T21's own
`tests/test_agents/test_loop.py` established), dropping `plan` for `chat`, leaving `report`
unbuilt, requiring a project argument on `history`/`why`, and folding session/round/mode from the
event log rather than adding new persisted state.

Tests: `tests/test_render/` — 24 tests (`test_status_board.py`, `test_question_card.py`,
`test_cli.py`), all zero-cost. Full suite re-run: 853 passed (829 baseline + 24 new), 1 skipped.

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
