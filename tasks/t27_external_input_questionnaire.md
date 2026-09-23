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

- [ ] A session where the user answers \"that's the client's call\" three times produces a sendable questionnaire
- [ ] Each question states why it matters and the provisional assumption in force
- [ ] Provisional assumptions are marked `provisional: true` and visibly flagged in REVIEW
- [ ] External-owned blocking items do **not** block READY — verified end-to-end
- [ ] The questionnaire is free of internal jargon and entity IDs
- [ ] `ppa client-questions` renders in markdown and honours the house style

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
