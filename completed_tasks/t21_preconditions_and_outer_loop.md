# T21 — Preconditions and the outer loop

| | |
|---|---|
| **Phase** | C · Orchestration and guardrails |
| **Estimate** | 1 day |
| **Needs a model?** | Yes — first agent invocation |
| **Design reference** | DESIGN.md §2.2, §2.10, §2.11, S6.3–S6.4, §1.11, §2.18 |

## Prerequisites

- [x] **T20**

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

- [x] Advancing to PLANNING with an open blocking requirement routes back to Discovery — **proven without a model in the loop**
- [x] All seven result classifications are handled explicitly; an unhandled one raises
- [x] `HUMAN_INPUT_REQUIRED` suspends cleanly and is not recorded as an error
- [x] A forced stub loop hits the cap, writes `anomaly.loop_cap_reached`, escalates, and is **not** recorded as completion
- [x] Completion is decided by `check_readiness()`, never by model output — assert no code path reads model text to decide completion
- [x] One full turn completes and produces one git commit with a meaningful message
- [x] The raw ledger is never placed in context — assert by inspection and by test
- [x] A 20-round fixture session stays within the configured context budget
- [x] Rounds beyond `N` are summarized into the digest, not dropped by generic compaction

## Traps

Do not try to reimplement the inner loop. The SDK owns it and fighting the harness will cost
days. What you control is which tools exist, what they return, and the hooks around them.

## Build record

`ppa/orchestrator/preconditions.py::validate_discovery_state` — plain Python, no model — reuses
`check_readiness` (T10) rather than duplicating its logic, but filters the returned blockers down
to the five conditions that are actually Discovery's own business (`DISCOVERY_EXIT_CONDITIONS`),
excluding the two that belong to REVIEW mode (`unresolved_conflict`, `review_not_approved` —
decision #19's still-not-buildable-before-T30 inputs). Without the filter, Discovery could never
validate in v1 at all, gated on facts nothing before T30 can ever supply.

`ppa/orchestrator/dispatch.py` — step 5 (`select_agent`, a `{"DISCOVERY": "discovery",
"DISCOVERY_VALIDATED": "planning"}` table lookup, matching DESIGN.md §2.5's own
`advance_to_planning` gate exactly) and step 7 (`invoke_agent`, a thin call into the already-built
`Agent.invoke()`). Only the two states v1 actually walks are wired; every other state raises
`UnwiredWorkflowState` naming exactly that, rather than guessing an agent mapping DESIGN.md never
specifies.

`ppa/orchestrator/context.py` — `assemble_context`: digest (T09, untouched) + up to `N` (default
6) recent rounds in full, older rounds summarized, never dropped. **A round is one outer-loop
transaction** — `rounds_from_events` groups `events.ndjson` by `txn_id`, keeping only transactions
that reached `txn.commit` (the same "no commit, it never happened" rule
`ppa.ledger.materialize._effective_events` applies to entity state), so the outer loop and its own
context history agree on round boundaries by construction. `DEFAULT_MAX_CONTEXT_TOKENS = 8_000`
is the budget a 20-round fixture is asserted against.

`ppa/orchestrator/loop.py` — `run_turn` (one outer-loop iteration, DESIGN.md §2.11 steps 1-10) and
`run_session` (step 11: call `run_turn` again until a stopping outcome or `iteration_cap`, a
runaway guard only). All seven `AgentResultStatus` members are handled by an explicit branch in
`_handle_result`; anything else raises `AssertionError` (tested by passing a
`types.SimpleNamespace` with a bogus `.status`, since a real `AgentResult` cannot construct with
an invalid one). `RECOVERABLE` retries up to `DEFAULT_RETRY_BUDGET` (3, DESIGN.md §2.14's own
number) inside `run_turn` itself before escalating — real backoff policy stays T32's job, this is
only the attempt count. Completion (`StepOutcome.COMPLETE`) is decided by `check_readiness()`
alone, checked *before* any agent is selected or invoked — a monkeypatched `select_agent` that
raises if called proves the agent is genuinely never touched on that path. `workflow_state` moves
by a direct `project.json` write (no dedicated event type exists for a pure state change, matching
`ppa.ledger.project.create_project`'s own precedent), followed by one `git commit` — either
`ppa.ledger.gitops.commit_turn` (derives its message from the round's own events) for a real turn,
or a one-line "routed back to DISCOVERY: ..." message for a precondition failure, since nothing
was written that turn for `commit_turn` to summarize.

**Decision #28** (`blockers.md`) covers four judgment calls the task file leaves implicit: the
Discovery-exit condition filter above; `select_agent`'s deliberately incomplete state table; why a
`WORKFLOW_TRANSITION` requesting `DISCOVERY_VALIDATED` is not re-gated inline (the *next*
`run_turn` call re-validates before invoking Planning regardless, so nothing is actually
skippable); and how "Needs a model: Yes" is satisfied. On that last point: every real `Agent`
(`DiscoveryAgent`/`PlanningAgent`/`DeliveryAgent`) still returns a stub `NOT_IMPLEMENTED` without
touching the SDK — T23+ builds real behavior, and `agents/base.py`/`agents/discovery.py` are not
in this task's own file scope. Following T01's own precedent (`scripts/verify_auth.py`, never
part of the pytest suite): the automated suite proves every outer-loop mechanic with a fixture
`Agent` (`tests/test_agents/test_loop.py`, 29 tests, zero cost), and a new one-off script,
`scripts/verify_first_turn.py`, proves the real thing. Run once during this task, subscription
auth, no API key: `provider: {'model': 'claude-sonnet-5', ...}` → `reply: 'TURN_OK'` → `cost:
0.1109` → `-> PASS`.

Full suite re-run: **677 passed, 1 skipped** (648 baseline + 29 new T21 tests).

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
