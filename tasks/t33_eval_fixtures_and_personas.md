# T33 — Eval fixtures and personas

| | |
|---|---|
| **Phase** | F · Resilience and validation |
| **Estimate** | 0.75 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.14, S12.1 |

## Prerequisites

- [ ] **T31**

## Why this task exists

You cannot improve what you do not measure, and without this you will tune prompts by vibes and
regress silently. Fixtures must be hard enough to break the agent — if none do, they are too easy
to be useful.

## What to build

### Ten seed requirements

Spanning the real spread:
- vague ↔ detailed
- B2B ↔ consumer
- greenfield ↔ legacy integration
- engineer-authored ↔ product-authored
- internal tool ↔ client project (exercises T27)

Keep them one or two lines each — that is what users actually type.

### Six scripted personas

| Persona | Behaviour |
|---|---|
| `knows_their_stuff` | Detailed, consistent answers |
| `vague` | Short, non-committal answers |
| `always_idk` | "I don't know" to everything — must still terminate (T26) |
| `contradicts_self` | Round 4 contradicts round 1 — must be caught (T30) |
| `impatient` | "Just build it", pushes to skip — gate must hold |
| `defers_to_client` | "That's the client's call" — must produce a questionnaire (T27) |

Each persona is a deterministic function from question → answer, so runs are reproducible.

## Files touched

```
tests/eval/fixtures/*.yaml
tests/eval/personas.py
tests/eval/harness.py
```

## Done when

- [ ] Ten fixtures, covering every axis listed above
- [ ] Six personas, each able to complete a session unattended
- [ ] **At least two fixtures break the agent on first run** — if none do, they are too easy
- [ ] Persona responses are deterministic and reproducible across runs
- [ ] A full fixture × persona run can be launched with one command

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T33: Eval fixtures and personas"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t33_*.md completed_tasks\
   bash:     mv tasks/t33_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T33` on the board.
