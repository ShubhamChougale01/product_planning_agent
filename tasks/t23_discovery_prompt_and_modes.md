# T23 — Discovery system prompt and internal modes

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 1 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.5, §2.5, §6.1, §6.4, S7.1–S7.3 |

## Prerequisites

- [ ] **T22**

## Why this task exists

The first prompt in the system. Everything that cannot be enforced by a tool has to be stated
here — and everything that *can* be enforced by a tool must **not** rely on being stated here.
Audit Part 1 of DESIGN.md line by line: each hard rule is either enforced in code or written
into this file. Anything in neither place will not happen.

## What to build

### `ppa/agents/prompts/discovery_core.md`

Must cover:

1. **Identity** — a product analyst and requirements engineer, not a chatbot or a questionnaire.
2. **Propose-and-confirm is the default** (§1.5). Never ask an open question when you can make a
   defensible proposal and ask for confirmation. Reaction is cognitively cheaper than generation,
   and the user may not have thought this through.
3. **Two exceptions to that default** (§6.4): `problem` and `users` must be *asked*, never
   proposed. A confident wrong proposal there gets accepted and you plan the wrong product
   convincingly.
4. **No silent assumptions, ever.** Every inference becomes an ASM with
   `user_confirmation_required`.
5. **Never re-ask the same question in the same form.** If a reframing also fails, escalate to a
   different route (T26).
6. **Narrate engine output; never recompute it.** Coverage, readiness, impact and dates come from
   tools. Do not do arithmetic.
7. **Role-conditioned vocabulary** (§6.1) — the profile is in context. For `engineer`, ask
   `nfr`/`data`/`platform` plainly and guide on `problem`/`success`. For `product`, invert.
8. **Today's date is injected every turn.** Never guess it.

### Autonomy thresholds — a table, not prose (§6.4)

```
May assume, notify only:   impact == LOW  AND  area not critical for this profile
Must confirm before READY: impact >= MEDIUM  OR  area is critical
Must ask, never assume:    problem, users
```

Config knob `autonomy: conservative | balanced | assertive` shifts only the assume-vs-ask
threshold. It never changes the never-silent rule.

### Mode fragments

`INTAKE / CLARIFY / GUIDANCE / RESEARCH / REVIEW / READY` — one prompt fragment and one tool
subset each. Enforced at the harness level via `allowed_tools`, not by asking the prompt nicely.

### Turn integration (S7.3)

One Discovery turn, wired to the outer loop built in T21:

```
read digest (T09)
  -> inject current date, current mode, user profile
  -> run the agent
  -> process tool calls
  -> evaluate the readiness gate (T10)
  -> return a structured AgentResult to the Orchestrator
```

The `AgentResult` is what the Orchestrator classifies into its seven outcomes (T21). Discovery
**never** decides that the task is complete — it reports state and the gate decides. An agent
that believes it is finished while blocking unknowns are open simply receives another turn.

## Files touched

```
ppa/agents/prompts/discovery_core.md
ppa/agents/prompts/mode_{intake,clarify,review}.md
ppa/agents/discovery.py  (extend)
ppa/agents/turn.py
tests/test_agents/test_modes.py
```

## Done when

- [ ] Every hard rule in DESIGN.md Part 1 is either tool-enforced or present in this prompt — audit line by line and record the mapping
- [ ] The agent cannot call `ask_user` in REVIEW mode — verified by test
- [ ] The agent cannot call `manage_requirement(create)` in READY mode
- [ ] Autonomy thresholds are a table in config, not prose in the prompt
- [ ] Current date is injected on every turn
- [ ] The prompt renders differently for `engineer` and `product` profiles
- [ ] One turn completes and returns a structured `AgentResult`, never a completion claim in prose

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_agents/`
3. Commit: `git add -A && git commit -m "T23: Discovery system prompt and internal modes"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t23_*.md completed_tasks\
   bash:     mv tasks/t23_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T23` on the board.
