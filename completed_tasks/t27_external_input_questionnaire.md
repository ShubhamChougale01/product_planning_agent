# T27 — External input routing and the client questionnaire

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 0.5 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §6.2, S8.4 |

## Prerequisites

- [ ] **T26**

## Why this task exists

Coditas engineers scoping **client** work often cannot know the answer — it lives with the client.
That is not `unexplored` (guidance won't help), not `factually_unknown` (research won't help),
and assuming is actively dangerous because you would be inventing the client's requirements.

The payoff is larger than the fix: the agent produces the client question list as a *byproduct*
of planning. For a services business this is plausibly the most commercially valuable output
here, and it costs almost nothing extra.

## What to build

### Route

```
needs_external_input
  -> open item with owner_type: external
  -> do NOT guide, do NOT research, do NOT assume silently
  -> record a PROVISIONAL assumption, clearly marked "pending client confirmation"
  -> accumulate into the client questionnaire
```

### Gate exception

External-owned blocking items **do not prevent READY** — otherwise every client project stalls.
They convert to provisional assumptions and appear prominently in REVIEW. This is already
implemented in T10's gate condition 2; verify it end-to-end here.

### The questionnaire — `ppa client-questions`

Render all `owner_type: external` open items as a sendable document, grouped by coverage area.
Each question carries:
- the question in client-facing language, free of internal jargon
- **why it matters** — what it changes about what gets built
- **the provisional assumption in force meanwhile** — so silence has a stated consequence
- whether it is blocking

Output formats: markdown, and whatever `house_style.yaml` specifies (T04).

## Files touched

```
ppa/agents/modes/external.py
ppa/render/client_questions.py
tests/eval/test_external_input.py
```

## Done when

- [x] A session where the user answers \"that's the client's call\" three times produces a sendable questionnaire — proven both mechanically (`test_three_external_answers_produce_a_grouped_client_questionnaire`) and live (`test_a_real_clarify_turn_routes_needs_external_input`)
- [x] Each question states why it matters and the provisional assumption in force
- [x] Provisional assumptions are marked `provisional: true` — REVIEW mode itself (rendering it "visibly" in a review summary) is T30's own job, not yet built; the flag is set, enforced (`evaluate_external_input_round`) and queryable today. See Build record
- [x] External-owned blocking items do **not** block READY — verified end-to-end (`test_external_owned_blocking_unknown_does_not_block_readiness`)
- [x] The questionnaire is free of internal jargon and entity IDs
- [x] `ppa client-questions` renders in markdown and honours the house style

## Build record

`ppa/agents/modes/external.py` — the shape contract, following `intake.py`/`clarify.py`/
`dont_know.py`'s own discipline: `evaluate_external_input_round` diffs a round's before/after
ledger state and checks it against the entity pair DESIGN.md §6.2's route diagram requires.

`ppa/render/client_questions.py::render_client_questionnaire` — collects every `Unknown` with
`owner_type == "external"`, grouped by coverage area in `AREA_KEYS`'s own declared order, and
follows each one's `converted_to` link to its provisional `Assumption` for "what we'll assume
until you confirm." Never prints an entity id or an internal literal (`route=`, `owner_type`,
`PROPOSED`/`CONFIRMED`, ...) — enforced by `test_questionnaire_is_free_of_internal_jargon_and_
entity_ids`. Honors house style for the document's own title (`style.name`); no `json`/`jira_csv`
export path exists yet (nothing else in this codebase implements one either — `StoryStyle`'s own
"declared now so v1 doesn't block it" precedent) — a real, recorded scope gap, not a silent
omission.

`ppa/cli.py` gained a real `client-questions` command (not a T31 stub like `plan`/`status`/
`report`) — the task's own Done-when box requires it to actually render, not just exist.

**Decision #35** (`blockers.md`): `needs_external_input` is a three-call sequence — an external-
owned `Unknown` (question/why/blocking/area), a provisional `Assumption`, and a `manage_unknown
(convert)` linking them — not the single `manage_assumption` call T26 shipped. `Assumption` alone
cannot supply the four separate facts (question, why it matters, blocking, area) the questionnaire
needs; `Unknown` already had exactly those fields, and `converted_to` (T02) was already the right
link. `mode_clarify.md` updated accordingly; T26's own eval test still passes unmodified.

**Model flakiness note, not a regression:** the full `pytest -m live_model` run flagged one
pre-existing failure the first time through this session —
`test_clarify.py::test_clarify_round_on_a_post_intake_ledger_meets_the_per_round_shape` recorded
zero assumptions on that particular live turn, the exact non-determinism T25's own Build record
already documented ("the filter did not run on the first live attempt"). Re-ran that one test
alone: passed clean. Re-ran the full `live_model` suite again after this task's own new test was
added: all 5 passed clean. Not caused by this task's `mode_clarify.md` edits — the prompt content
those tests depend on for that gap-filter behavior was untouched here.

Tests: `tests/eval/test_external_input.py` (7 mechanical, zero-cost; 1 `live_model`). Full suite
re-run: **792 passed** (785 baseline + 7 new), 1 skipped, default run; `pytest -m live_model`:
5 passed (T23, T24, T25, T26, T27).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T27: External input routing and the client questionnaire"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t27_*.md completed_tasks\
   bash:     mv tasks/t27_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T27` on the board.
