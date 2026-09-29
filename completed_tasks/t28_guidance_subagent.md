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

- [x] Returns a schema-valid `GuidanceBrief` with ≥2 options and a reasoned recommendation — enforced by a pydantic validator, proven both mechanically and live
- [x] Rendered output reads like a colleague explaining a trade-off — no raw JSON reaches the user
- [x] The brief persists as `RES-nnn` linked to the resulting `DEC-nnn`
- [x] `ppa why <dec-id>` can answer \"why did we choose this?\" from the ledger alone
- [x] Deferring produces a DECIDE_LATER **and** a safe-default ASM so planning continues
- [x] Subagent context is isolated — a long research detour does not enlarge the main context — structural (its own `ClaudeSDKClient`, own conversation, own grant, never appended to Discovery's), proven by asserting the server only ever exposes Guidance's own tools
- [x] The subagent can write `RES-nnn`; the Discovery Agent cannot

## Build record

`ppa/agents/subagents/guidance.py` — `GuidanceBrief`/`GuidanceOption`/`GuidanceRecommendation` are
real, validated Pydantic models (`options` enforced at ≥2 by a field validator, not just a test
assertion). `run_guidance_session` finds the lowest-id `Unknown(route=GUIDANCE, status=OPEN)`,
runs its own isolated SDK turn (own `ClaudeSDKClient`, own `subagent_guidance.md` system prompt,
own grant-scoped in-process MCP server — `_guidance_server_and_allowed_tools`), and parses the
model's own final reply as the brief (`parse_guidance_brief`, tolerant of an accidental markdown
fence). `GuidanceAgent.invoke(ctx)` is now a thin wrapper over this.

`ppa/render/guidance_card.py` — `render_guidance_brief` turns a validated brief into prose (no
`{`/`}` ever reaches the output); `render_why` answers "why did we choose this?" by following a
`Decision`'s own fields plus any `ResearchFinding.feeds_decision` pointing at it. `ppa/cli.py`
gained a real `why` command (not a T31 stub, matching T27's `client-questions` precedent).

**Decision #36** (`blockers.md`): four related judgment calls, all logged there in one entry —
`manage_research` (create/link_decision/supersede) built from scratch in `discovery_tools.py`
(nothing before this task ever needed to write a real `ResearchFinding`); `link_decision` as a
separate operation with its own new `EventType` (`feeds_decision` genuinely cannot be known until
*after* the research, per DESIGN.md's own sequence); `GuidanceAgent` deriving its own topic from
ledger state rather than an extended `InvocationContext`; and the subagent stopping at step 6
(never landing the decision itself — its grant structurally cannot).

**Model flakiness note, not a regression:** the same pre-existing `test_clarify.py` flake already
documented in T25's and T27's own Build records recurred once more on this session's first full
`live_model` run (zero assumptions recorded on that particular live CLARIFY turn) — unrelated to
any file this task touches. This task's own new live test
(`test_a_real_guidance_session_produces_a_schema_valid_brief_and_persists_it`) passed clean on its
first run.

Tests: `tests/eval/test_guidance.py` (11 mechanical, zero-cost; 1 `live_model`). Full suite
re-run: **803 passed** (792 baseline + 11 new), 1 skipped, default run; `pytest -m live_model`:
6 passed (T23, T24, T25 — after the noted flake — T26, T27, T28).

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
