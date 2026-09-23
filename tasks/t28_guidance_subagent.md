# T28 — Guidance Mode subagent

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 1.25 day |
| **Needs a model?** | Yes + web |
| **Design reference** | DESIGN.md §1.7, §3.5, S9.1–S9.3 |

## Prerequisites

- [ ] **T26**

## Why this task exists

Guidance is a conversation with a different posture, not a tool returning data — which is why it
is a **subagent** with its own prompt, own grant and isolated context. Isolation matters: a long
research detour must not pollute the clarification context.

## What to build

### Subagent

Own prompt, own grant: `read_planning_state` + `manage_research` (+ web search). Registered in
T14. It is the *only* thing that can write `RES-nnn` — correct, because findings should be
written by whatever did the work.

### Sequence

1. **Restate plainly.** Strip jargon; confirm it is the right question.
2. **Explain the stakes** — what breaks later if this is wrong, concretely, referencing *this*
   product rather than generically.
3. **Narrow with sub-questions.** For target users: *"When you imagine someone opening this, are
   they doing their own job, or managing someone else's?"* — far easier to answer than the original.
4. **Research** if the question is factual.
5. **Present 2–4 options** with pros, cons, and "best when".
6. **Recommend one**, with reasoning and confidence.
7. **Land it** — user picks, or defers (→ DECIDE_LATER with a safe default recorded as an ASM so
   planning continues).

### GuidanceBrief

```json
{ "dont_know_kind": "...", "restated_plainly": "...", "why_it_matters": "...",
  "what_it_affects": ["REQ-003", "scope_in"],
  "options": [{"name","description","pros","cons","best_when"}],
  "recommendation": {"option","because","confidence"},
  "what_would_settle_it": "...", "safe_default_if_deferred": "...",
  "researched": true, "sources": [] }
```

**The main agent renders this conversationally.** It never dumps JSON at the user. Structure is
for the ledger and for replay; prose is for the human.

### Persistence

The brief is written as `RES-nnn` linked to the resulting `DEC-nnn`, so `ppa why DEC-004` can
answer *"why did we choose this?"* long after the conversation.

## Files touched

```
ppa/agents/subagents/guidance.py
ppa/agents/prompts/subagent_guidance.md
ppa/render/guidance_card.py
tests/eval/test_guidance.py
```

## Done when

- [ ] Returns a schema-valid `GuidanceBrief` with ≥2 options and a reasoned recommendation
- [ ] Rendered output reads like a colleague explaining a trade-off — no raw JSON reaches the user
- [ ] The brief persists as `RES-nnn` linked to the resulting `DEC-nnn`
- [ ] `ppa why <dec-id>` can answer \"why did we choose this?\" from the ledger alone
- [ ] Deferring produces a DECIDE_LATER **and** a safe-default ASM so planning continues
- [ ] Subagent context is isolated — a long research detour does not enlarge the main context
- [ ] The subagent can write `RES-nnn`; the Discovery Agent cannot

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T28: Guidance Mode subagent"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t28_*.md completed_tasks\
   bash:     mv tasks/t28_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T28` on the board.
