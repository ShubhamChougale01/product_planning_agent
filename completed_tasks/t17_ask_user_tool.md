# T17 — ask_user and the four affordances

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.4, §3.2, S5.6 |

## Prerequisites

- [x] **T16**

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

- [x] A 6-question batch is rejected as VALIDATION
- [x] A question missing `why_asked` is rejected
- [x] All four `answer_kind` values round-trip correctly
- [x] Every question is persisted as `Q-nnn` and every answer as `ANS-nnn`
- [x] Answers pass through secret scanning before being written
- [x] `not_relevant` records a reason rather than discarding the question

## Build record

Built `ppa/tools/interaction.py` (`ask_user`) and a minimal `ppa/render/question_card.py`
(`render_question_card`/`render_answer_summary`, formatting only — no terminal I/O; that is T31's
job). `ask_user` does not itself collect answers from a live surface: each question dict may carry
an already-obtained `answer` sub-dict, the same way `manage_*` writers (T16) don't care whether a
free-text field came from a model or a person.

**Two id series, three events for an answered question**, matching `QuestionAnswer`'s own docstring
("`Q-nnn` while awaiting an answer, `ANS-nnn` once one is recorded") literally rather than mutating
one record's id in place: `QUESTION_ASKED` creates `Q-nnn` (`PENDING`), `QUESTION_REPLACED` moves
that same `Q-nnn` to `REPLACED` (superseded, never mutated), `ANSWER_RECORDED` creates a *new*
`ANS-nnn` (`ANSWERED`) carrying every question field plus the answer. A question asked with no
embedded answer stops after step 1, staying `Q-nnn`/`PENDING` — the shape T31's real CLI will
produce before it has collected a response.

**Scope boundaries kept deliberately narrow**, both stated directly in the module docstring:
`decide_later` does not open a `DEC-nnn` Decision from inside this module (that is T26's routing
table, built on top of `manage_decision`, already granted to Discovery); `dont_know`'s
`dont_know_kind` classification is likewise T26's job — this module only records the raw affordance
and passes through whatever classification the caller already supplies, if any.

Audit is self-recorded per event (one record per `QUESTION_ASKED`/`QUESTION_REPLACED`/
`ANSWER_RECORDED`), same reasoning and same open item for T19 as T16's writers (decision #24,
`blockers.md`) — a rejected batch gets exactly one `reject` audit record, an answered question gets
three `write` records.

Tests: `tests/test_tools/test_ask_user.py`, 18 tests. Full suite re-run: **574 passed**
(556 baseline + 18).

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
