# T17 — ask_user and the four affordances

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.4, §3.2, S5.6 |

## Prerequisites

- [ ] **T16**

## Why this task exists

This is the interaction contract. Every question the user ever sees goes through here, which
makes it the right place to enforce the batch cap and the guarantee that "I don't know" is
always a first-class option rather than a failure.

## What to build

### Tool

```
ask_user(questions: list[Question]) -> ToolResult[list[Answer]]
```

**At most 5 questions per call; 3 is the target.** A 6-question batch is rejected as VALIDATION.

Each `Question` carries:
- `text` — plain language, no jargon
- `why_asked` — one line. This is what turns a questionnaire into a partner; it is **required**
- `target_areas` — which coverage areas this would move
- `suggested_options` — 2–4 concrete options where they exist
- `recommended_default` — with a one-line reason

Each `Answer` returns `answer_kind`:

| | |
|---|---|
| `answered` | free text |
| `dont_know` | routed to the classifier (T26) |
| `decide_later` | becomes a DECIDE_LATER decision |
| `not_relevant` | closed with a reason, not silently dropped |

### Rendering

The CLI renderer is built properly in T31. Here, a minimal renderer is enough to round-trip all
four affordances in a test.

## Files touched

```
ppa/tools/interaction.py
ppa/render/question_card.py  (minimal)
tests/test_tools/test_ask_user.py
```

## Done when

- [ ] A 6-question batch is rejected as VALIDATION
- [ ] A question missing `why_asked` is rejected
- [ ] All four `answer_kind` values round-trip correctly
- [ ] Every question is persisted as `Q-nnn` and every answer as `ANS-nnn`
- [ ] Answers pass through secret scanning before being written
- [ ] `not_relevant` records a reason rather than discarding the question

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_tools/`
3. Commit: `git add -A && git commit -m "T17: ask_user and the four affordances"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t17_*.md completed_tasks\
   bash:     mv tasks/t17_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T17` on the board.
