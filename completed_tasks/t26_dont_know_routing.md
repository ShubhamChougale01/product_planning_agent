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

- [x] Fixtures for all **seven** kinds classify correctly — proven both mechanically (`tests/eval/test_dont_know.py`'s direct-writer tests, one per kind) and live (`test_a_real_clarify_turn_classifies_and_routes_all_seven_kinds`, a real CLARIFY turn given all seven signals at once)
- [x] `dont_understand` never triggers research — `ppa.providers.research` is still an empty stub until T29, nothing to spy on yet, so this asserts the structural proxy available today: no `Unknown(route=RESEARCH)` or `ResearchFinding` results from this kind. See Build record
- [x] `no_opinion` produces an ASM with `user_confirmation_required`
- [x] `not_my_call` produces a DEC with `owner_type != user`
- [x] `factually_unknown` produces an UNK with `route=RESEARCH`
- [x] A blocking research item is recorded as `blocking=true, route=RESEARCH`
- [x] The `always_idk` persona terminates, with tracked assumptions and deferred decisions, never an empty loop — **resolved at T34**: a real 6-round session (`tests/eval/test_decisions_33_34_clarify_session_level.py`) shows the anti-loop guard's forced escalation actually firing against real ledger state (a blocking `Unknown(route="GUIDANCE")` present by the end) and no question ever repeated verbatim — not just `simulate_always_idk_termination`'s arithmetic proof in isolation. See blockers.md decision #34.
- [x] No question is ever re-asked in identical form

## Build record

`ppa/engines/dont_know_classifier.py` — the deterministic quarter of this task, the same
"engines are deterministic, agents narrate" split every earlier engine in this codebase draws:
the seven kinds named once (`DONT_KNOW_KINDS`), the routing table as code (`ROUTE_FOR_KIND`,
matching DESIGN.md §3.4 exactly), which two kinds justify an expensive path (`EXPENSIVE_KINDS`),
and the anti-loop guard's own arithmetic (`MAX_REFRAME_ATTEMPTS`, `should_force_escalation`,
`is_same_question`, `simulate_always_idk_termination`). Matching a raw "I don't know" signal to
one of the seven kinds is inherently qualitative — the model's own job, guided by the routing
table `mode_clarify.md` now carries (added a `## "I don't know" is at least seven different
things` section, plus a strengthened `discovery_core.md` note on the two-reframe limit).

`ppa/agents/modes/dont_know.py::evaluate_dont_know_routing` — the shape contract, following
`intake.py`/`clarify.py`'s own discipline exactly: diffs a round's before/after ledger state and
checks it against the entity the routing table says that kind must produce, never trusting the
model's own claimed text.

**No new MCP tool was needed.** Every route in the table is reachable with `ask_user`,
`manage_assumption`, `manage_decision` and `manage_unknown`, all already built by T16/T17 —
`unexplored` and the anti-loop guard's forced escalation both record an `Unknown` with
`route="GUIDANCE"` (a real estimate of a literal `Unknown.route` already ships with since T02),
`needs_external_input` records a provisional `Assumption`, and `depends_on_x` records an
`Unknown` with `route="USER_DECISION"`.

**Bug #13** (`blockers.md`): building the `needs_external_input` test live surfaced that
`manage_assumption`'s own `ToolSpec` never exposed `provisional` to the model, even though the
writer and the MCP coercion layer both already handled it — a real model call had no way to ever
set it. Fixed by adding it to `MANAGE_ASSUMPTION_SPEC.inputs`/`.optional`.

**Decision #34** (`blockers.md`, pending, resolve at T33/T34): the same shape of gap decision #33
already logged for T25 — the `always_idk` persona and a real multi-round session are T33/T34's
own artifacts. `simulate_always_idk_termination` proves the anti-loop guard's arithmetic
deterministically (bounded asks, never a repeat, forced escalation at the threshold); a
persona-driven live proof through several stuck questions in a row is left honestly for later.

Tests: `tests/eval/test_dont_know.py` (13 mechanical, zero-cost; 1 `live_model`). Full suite
re-run: **785 passed** (771 baseline + 14 new), 1 skipped, default run; `pytest -m live_model`:
4 passed (T23's real-turn test, T24's intake eval, T25's clarify eval, T26's dont-know eval).

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
