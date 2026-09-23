# T21 — Preconditions and the outer loop

| | |
|---|---|
| **Phase** | C · Orchestration and guardrails |
| **Estimate** | 1 day |
| **Needs a model?** | Yes — first agent invocation |
| **Design reference** | DESIGN.md §2.2, §2.10, §2.11, S6.3–S6.4, §1.11, §2.18 |

## Prerequisites

- [ ] **T20**

## Why this task exists

The most important structural idea in the design: **there are two loops**. The inner loop is the
SDK's, driven by `stop_reason`. The outer loop is ours, driven by workflow state and the
readiness gate. Task completion is never a model decision — an agent that stops with three
blocking unknowns open simply gets another turn.

## What to build

### Preconditions — called directly, never requested from the model

```python
def advance_to_planning(ledger):
    result = preconditions.validate_discovery_state(ledger)   # plain Python
    if not result.ok:
        return route_back_to_discovery(result.blockers)
    return invoke(PlanningAgent, scoped_context(ledger))
```

The model cannot skip mandatory validation **because the model is never asked to perform it**.
This is stronger than forced `tool_choice`, and it does not depend on SDK internals. Where the
model should genuinely choose, leave `tool_choice` on auto.

### Outer loop — `ppa/orchestrator/loop.py`

```
 1 load ledger -> digest, workflow state, ledger_version
 2 evaluate readiness gate                      (deterministic, T10)
 3 gate passed and state terminal -> COMPLETE
 4 validate preconditions for next state        (deterministic)
 5 select agent from workflow state             (table lookup)
 6 open transaction (txn_id, checkpoint)
 7 invoke agent  ------> inner loop, SDK-managed
 8 receive structured AgentResult
 9 classify (7 outcomes):
      OK · PARTIAL · RECOVERABLE · NON_RECOVERABLE ·
      HUMAN_INPUT_REQUIRED · WORKFLOW_TRANSITION · NOT_IMPLEMENTED
10 OK/PARTIAL           -> validate, commit txn, regenerate digest, git commit
   RECOVERABLE          -> retry budget at this level
   HUMAN_INPUT_REQUIRED -> surface question, suspend. NOT an error
   WORKFLOW_TRANSITION  -> update state, loop
   NON_RECOVERABLE      -> roll back txn, preserve partials, escalate
11 loop
```

The session iteration cap is a **runaway guard only**. Reaching it writes
`anomaly.loop_cap_reached` and escalates — it never counts as completion.

### Context assembly — what the agent actually sees each turn

The loop is what builds the context, so it owns this. By round eight a real session has a long
history; without a policy the agent either overruns the window or gets generically compacted,
which silently destroys the structure the digest was built to preserve.

**Policy:** `system prompt + digest + last N turns`. **Never the raw ledger** — that is what the
digest exists for.

- Make `N` configurable, default 6 turns. Measure before tuning it.
- When history exceeds `N`, **summarize the older rounds into the digest** rather than letting
  generic compaction eat them. A round summarizes to: questions asked, answers received, entities
  created. Everything else is already in the ledger and is retrievable by query.
- Log the assembled context size per turn so T35's cost instrumentation has something to read.
- Assert an upper bound in tests: a 20-round fixture session must not exceed the configured
  context budget.

The reason this is a rule and not a nicety: the digest (T09) is deliberately asymmetric — blocking
items in full, everything else as titles. Generic compaction does not know that and will drop
blocking items to save tokens on a long conversation.

## Files touched

```
ppa/orchestrator/loop.py
ppa/orchestrator/preconditions.py
ppa/orchestrator/dispatch.py
ppa/orchestrator/context.py
tests/test_agents/test_loop.py
```

## Done when

- [ ] Advancing to PLANNING with an open blocking requirement routes back to Discovery — **proven without a model in the loop**
- [ ] All seven result classifications are handled explicitly; an unhandled one raises
- [ ] `HUMAN_INPUT_REQUIRED` suspends cleanly and is not recorded as an error
- [ ] A forced stub loop hits the cap, writes `anomaly.loop_cap_reached`, escalates, and is **not** recorded as completion
- [ ] Completion is decided by `check_readiness()`, never by model output — assert no code path reads model text to decide completion
- [ ] One full turn completes and produces one git commit with a meaningful message
- [ ] The raw ledger is never placed in context — assert by inspection and by test
- [ ] A 20-round fixture session stays within the configured context budget
- [ ] Rounds beyond `N` are summarized into the digest, not dropped by generic compaction

## Traps

Do not try to reimplement the inner loop. The SDK owns it and fighting the harness will cost
days. What you control is which tools exist, what they return, and the hooks around them.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_agents/`
3. Commit: `git add -A && git commit -m "T21: Preconditions and the outer loop"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t21_*.md completed_tasks\
   bash:     mv tasks/t21_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T21` on the board.
