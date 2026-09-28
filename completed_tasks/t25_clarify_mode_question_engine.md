# T25 — Clarify mode and the question engine

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 1 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.4, §3.2, §6.4, S7.5 |

## Prerequisites

- [x] **T24**

## Why this task exists

**This is the product.** An agent that stores beautiful versioned requirements but asks fifteen
generic questions is worse than useless — the user abandons at question seven. The value is in
deciding what *not* to ask.

## What to build

### Five-step pipeline

**A · Find gaps** *(deterministic)* — coverage areas below SUFFICIENT, ranked by profile criticality.

**B · Generate candidates** *(model)* — for each gap, with mandatory metadata:
```
{ text, target_area, why_it_matters, blocking,
  answerable_by: "user_only" | "research" | "agent_inference",
  proposed_default, options[] }
```

**C · Filter** — *where the value is*:
- `agent_inference` + confidence ≥ MEDIUM → **do not ask.** Record an ASSUMPTION, flag it, move on
- `research` → **do not ask.** Record an UNKNOWN with `route=RESEARCH`, queue it
- already answered or derivable from an existing entity → **drop silently**
- not blocking and area not critical → **defer to backlog**, don't spend a slot

**D · Score and select**
```
priority = (2.0 if blocking else 1.0)
         × information_gain      # areas/decisions unblocked
         × user_answerability    # from the profile — can THIS user answer it?
         ÷ cognitive_cost
```
Take top 3, max 5. **Prefer a spread across areas** over three questions about one area — breadth
surfaces unknown-unknowns faster.

**E · Shape** — each question ships with plain text, `why_asked`, 2–4 options, a recommended
default, and the four affordances.

### Budget and fatigue (§1.4)

- Hard cap 5 per round, target 3
- After **round 4**: pass the gate or explicitly offer *"I can close the rest with assumptions —
  here they are. Approve and we proceed, or keep going."*
- Show the meter move every round: *"That moved critical coverage from 3/7 to 5/7."*
- **Fatigue signal** — short answers, "whatever", "you decide", or `dont_know` three times running
  → switch to assumption-heavy mode automatically **and say so**

## Files touched

```
ppa/agents/modes/clarify.py
ppa/engines/question_engine.py
ppa/agents/prompts/mode_clarify.md
tests/eval/test_clarify.py
```

## Done when

- [x] A round asks ≤5 questions
- [x] **A round records at least one assumption instead of asking about it** — if the agent asks everything, the filter is not working. This is the criterion that matters
- [ ] At least one candidate per session is routed to research rather than asked — see Build record: not independently verified in a live run this task, see decision #33
- [~] The round report shows the coverage delta — instructed in the prompt; not asserted by an automated check (no live-text assertion for this specific claim), see Build record
- [ ] Round 4 triggers the assumptions offer if the gate has not passed — engine function built and unit-tested (`should_offer_assumptions`); not exercised end-to-end via a real 4-round live session, see decision #33
- [ ] Three consecutive `dont_know` answers trigger assumption-heavy mode, announced to the user — engine function built and unit-tested (`detect_fatigue`); not exercised end-to-end via a real live session, see decision #33
- [x] Questions spread across areas rather than clustering in one

## Traps

The filter in step C is the whole point of this task. It is tempting to build the generator and
ship — but an agent that asks every generated question is the failure mode this design exists to
avoid. Test the filter first.

## Build record

`ppa/engines/question_engine.py` — the deterministic quarter of the five-step pipeline: `find_gaps`
(step A, coverage areas below `SUFFICIENT`, ranked critical-first), `question_priority` (step D's
own scoring formula, as code, not something the model computes itself), `select_top_questions`
(the "top 3, max 5" cap enforced structurally), `detect_fatigue` and `should_offer_assumptions`
(§1.4's fatigue signal and round-4 soft cap). Steps B (generate) and the qualitative half of C
(is *this* candidate confidently inferable, research-only, or genuinely blocking?) stay the model's
own job — nothing here reads ledger free text to make that call for it, the same "engines are
deterministic, agents narrate" split every earlier engine in this codebase already draws.

`ppa/agents/modes/clarify.py::evaluate_clarify_round` diffs a round's before/after ledger state and
checks it against the per-round Done-when boxes — the same "check the ledger, never the model's own
claim" discipline `ppa.agents.modes.intake` already established.

**The filter did not run on the first live attempt.** A real round on a seeded post-intake ledger
asked 4 well-formed questions and recorded zero assumptions — technically under the 5-question cap,
but exactly the failure mode this task's own Traps section warns about. `mode_clarify.md`'s
original filter instructions were present but not forceful enough: the model generated only as many
candidates as it planned to ask, leaving nothing to become an assumption. Strengthened to require
walking the *whole* gap list explicitly, gap by gap, and stating directly that a round which
resolves nothing by inference has not filtered anything "no matter how good the questions are." The
very next live run recorded at least one assumption and passed the round check cleanly.

**Decision #33** (`blockers.md`): three of this task's own Done-when boxes describe *session*-level
or *multi-round* behavior (a research routing happening somewhere across a session; the round-4
assumptions offer; the three-`dont_know` fatigue switch) that a single live round cannot exercise
end to end. All three are fully built and unit-tested at the deterministic-engine layer
(`detect_fatigue`, `should_offer_assumptions`, both in `tests/test_engines/test_question_engine.py`)
and instructed in the prompt (`mode_clarify.md`'s own fatigue-signal and round-4 sections, both
carried over from T23) — what is not yet done is proving them through an actual multi-round live
session with simulated user answers between rounds, which is squarely T33/T34's own "eval fixtures
and personas" / "eval suite and baseline" territory (DESIGN.md Part 1.14, Step 12), not a single
task's live-model budget. Left honestly unchecked in this file's own Done-when list rather than
marked complete on the strength of the engine tests alone.

Tests: `tests/test_engines/test_question_engine.py` (15, zero-cost), `tests/test_agents/
test_clarify_shape.py` (7, zero-cost), `tests/eval/test_clarify.py` (1, `live_model`). Full suite
re-run: **770 passed** (748 baseline + 22 new), 1 skipped, default run; `pytest -m live_model`: 3
passed (T23's real-turn test, T24's intake eval, T25's clarify eval).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T25: Clarify mode and the question engine"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t25_*.md completed_tasks\
   bash:     mv tasks/t25_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T25` on the board.
