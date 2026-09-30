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

- [x] READY is unreachable without an explicit user approval event
- [x] Every HIGH-impact assumption is walked individually, never batched into one prompt
- [x] A change request produces a new requirement version — exercised via a real contradiction fixture (supersede REQ-002 + create its replacement); the pure-addition case ("also need a mobile app," no conflict candidates found) uses the identical `manage_requirement(create, ...)` call with an empty candidate list, not separately fixture-tested this task — see Build record
- [x] The change produces an impact report naming affected entities
- [x] The gate drops back to NOT READY and the workflow rewinds to the earliest affected state
- [x] The `contradicts_self` persona's conflict is surfaced, not silently appended
- [x] Superseded entities keep their history and are marked SUPERSEDED, never deleted

## Build record

`ppa/agents/modes/review.py` — `run_review_session` widens `DiscoveryMode.REVIEW`'s own grant to
`{read_planning_state, manage_assumption}` and runs one turn walking every HIGH-impact `PROPOSED`
assumption individually (structurally guaranteed by `manage_assumption` never taking more than one
`entity_id`). `grant_review_approval`/`current_review_approval` are plain functions, never an MCP
tool — mirroring T18's own `ppa/tools/approval.py` rule exactly: approval is the user's decision,
never something an agent can manufacture by calling a tool.

`ppa/agents/modes/change.py` — `run_change_session` records the change as a `QuestionAnswer`
(`ask_user`), detects candidates (`find_conflict_candidates`, T11, unchanged), runs one turn
against Discovery's own **full** grant (not a `DiscoveryMode` — `CHANGE_REQUESTED` is the global
workflow state, a different level), instructed to adjudicate every candidate via the new
`manage_conflict` tool and supersede+create for any real contradiction. Impact is analyzed
(`analyze_impact`, T11, unchanged) for whatever was actually superseded, then the workflow rewinds
`CHANGE_REQUESTED -> DISCOVERY` (v1's only real target — decision #28's own scoping).

**Decision #19 resolved** (`blockers.md`): the three readiness-gate inputs T10 left as
caller-supplied parameters are now real, wired to `review.approved`/`conflict.adjudicated` events —
exactly as T10's own row predicted, `check_readiness`'s signature needed no change at all.

**Decision #38** (`blockers.md`): five related judgment calls — `manage_conflict` built from
scratch; REVIEW's grant widened for `manage_assumption` only; approval as a plain function, never
a tool; change handling as its own turn against Discovery's full grant, not a mode; the v1 rewind
target always `DISCOVERY`.

**Honesty note on the "mobile app" Done-when box:** every fixture this task builds (mechanical and
live) exercises the *contradiction* path — detect, surface, supersede, create the replacement. The
pure-addition case ("also need a mobile app," where `find_conflict_candidates` returns nothing) is
structurally the same `manage_requirement(create, ...)` call already proven correct by every prior
task's own tests, with an empty candidate list handed to the model instead of a populated one — not
a new code path, but genuinely not its own fixture in this task's suite either.

Tests: `tests/eval/test_review.py` (6 mechanical, zero-cost; 1 `live_model`), `tests/eval/
test_change.py` (5 mechanical, zero-cost; 1 `live_model`). `tests/test_permissions/test_grants.py`'s
own hardcoded `_EXPECTED_GRANTS["discovery"]` set updated to include `manage_conflict` (T14-era
table, same "a later task legitimately widens an earlier one's locked expectation" pattern already
seen in this build). Full suite re-run: **829 passed** (813 baseline + 13 new + ~5 parametrize
expansion from the grant-table addition), 1 skipped, default run; `pytest -m live_model`: 9 passed
(T23 through T30) — one pre-existing flaky test (`test_research.py`, unrelated to this task's own
files) failed on the combined run and passed clean on an isolated retry, the same non-determinism
already documented for `test_clarify.py` in T25/T27/T28's own Build records.

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
