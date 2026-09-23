# T26 — \"I don't know\" classification and routing

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 1 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.6, §3.3, §3.4, S8.1–S8.3 |

## Prerequisites

- [ ] **T25**

## Why this task exists

"I don't know" is a valid product-planning state, never an error. But it is at least seven
different situations needing seven different responses — routing "what do you mean?" into a
research subagent wastes tokens and insults the user.

## What to build

### Classify first, route second

| Kind | Signal | Route |
|---|---|---|
| `dont_understand` | "What do you mean?" | Rephrase plainly, re-ask. **No research.** Cheap |
| `no_opinion` | "Whatever you think" | Propose a default → ASSUMPTION, confirmation required |
| `depends_on_x` | "Depends on the budget" | Record dependency, ask about X **first**, return later |
| `not_my_call` | "That's the CTO's decision" | DECISION, owner ≠ user, DECIDE_LATER + date |
| `unexplored` | "Haven't thought about it" | **Full Guidance Mode** (T28) |
| `factually_unknown` | "Which DB scales better?" | UNKNOWN `route=RESEARCH`, agent owns it |
| `needs_external_input` | "That's the client's call" | T27 — external owner, provisional assumption |

Only `unexplored` and `factually_unknown` justify the expensive paths.

### Classification maps to entity fields

Recall from T02 that `Unknown` has **two** fields. A blocking question that needs research is
`blocking=true, route=RESEARCH` — the case a single enum could not express.

### Anti-loop guard

Track reframe attempts per question. **After two, force escalation to a different route.** The
agent must never re-ask the same question in the same form. A user answering "I don't know" to
everything must still reach a terminal state, with the ledger full of tracked assumptions and
deferred decisions rather than an empty loop.

## Files touched

```
ppa/agents/modes/dont_know.py
ppa/engines/dont_know_classifier.py
tests/eval/test_dont_know.py
```

## Done when

- [ ] Fixtures for all **seven** kinds classify correctly
- [ ] `dont_understand` never triggers research — assert the research provider is not called
- [ ] `no_opinion` produces an ASM with `user_confirmation_required`
- [ ] `not_my_call` produces a DEC with `owner_type != user`
- [ ] `factually_unknown` produces an UNK with `route=RESEARCH`
- [ ] A blocking research item is recorded as `blocking=true, route=RESEARCH`
- [ ] The `always_idk` persona terminates, with tracked assumptions and deferred decisions, never an empty loop
- [ ] No question is ever re-asked in identical form

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T26: \"I don't know\" classification and routing"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t26_*.md completed_tasks\
   bash:     mv tasks/t26_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T26` on the board.
