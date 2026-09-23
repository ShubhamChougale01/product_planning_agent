# T25 — Clarify mode and the question engine

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 1 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.4, §3.2, §6.4, S7.5 |

## Prerequisites

- [ ] **T24**

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

- [ ] A round asks ≤5 questions
- [ ] **A round records at least one assumption instead of asking about it** — if the agent asks everything, the filter is not working. This is the criterion that matters
- [ ] At least one candidate per session is routed to research rather than asked
- [ ] The round report shows the coverage delta
- [ ] Round 4 triggers the assumptions offer if the gate has not passed
- [ ] Three consecutive `dont_know` answers trigger assumption-heavy mode, announced to the user
- [ ] Questions spread across areas rather than clustering in one

## Traps

The filter in step C is the whole point of this task. It is tempting to build the generator and
ship — but an agent that asks every generated question is the failure mode this design exists to
avoid. Test the filter first.

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
