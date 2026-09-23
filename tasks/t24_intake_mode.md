# T24 — Intake mode — the opening move

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 0.5 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §3.1, S7.4 |

## Prerequisites

- [ ] **T23**

## Why this task exists

The worst version of this product opens with "Tell me about your target users." The best version
opens by demonstrating it already understood something. This single behaviour earns more trust,
and harvests more corrections, than any question would.

## What to build

### Flow — before any question is asked

1. Write a **3–6 sentence Initial Product Understanding** — what is being built, for whom, why.
2. Draft **3–8 requirements as PROPOSED**, with LOW/MEDIUM confidence and a stated basis.
3. Record **every inference as an ASSUMPTION** with `user_confirmation_required: true`.
4. Coverage moves as a *consequence* of steps 2–3 — the engine recomputes. The agent never
   declares a coverage state (§2.7).
5. Ask exactly **one** thing: *"Where am I wrong?"*

### Why one question

Intake is not the place to start interrogating. A user who has just seen the agent understand
their idea will correct it freely; a user facing five questions will disengage. The corrections
are worth more than the answers.

### Example shape

> From *"a tool for tracking vendor invoices"* I'm reading this as an internal tool for an
> accounts-payable clerk processing 50–200 invoices a week, with a finance manager approving.
> I've assumed web-only and single-company — flagged both. Where am I wrong?

## Files touched

```
ppa/agents/modes/intake.py
ppa/agents/prompts/mode_intake.md
tests/eval/test_intake.py
```

## Done when

- [ ] On *\"a tool for tracking vendor invoices\"* it produces ≥3 proposed requirements
- [ ] It produces ≥2 assumptions, all flagged for confirmation
- [ ] It asks exactly **one** question
- [ ] Zero assumptions are silent — every inference is an ASM entity
- [ ] Coverage state after intake is computed, never declared — no coverage setter is called
- [ ] The understanding statement is 3–6 sentences, not a wall of text

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T24: Intake mode — the opening move"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t24_*.md completed_tasks\
   bash:     mv tasks/t24_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T24` on the board.
