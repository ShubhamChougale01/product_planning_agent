# T20 — Agent protocol and workflow state machine

| | |
|---|---|
| **Phase** | C · Orchestration and guardrails |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.4, §2.5, S6.1–S6.2 |

## Prerequisites

- [x] **T18**

## Why this task exists

Three agents and four subagent/stub registrations, with the workflow they move through. The
state machine is data, not conditionals, so guardrails are inspectable and testable without
running a model.

## What to build

### Agent protocol — `ppa/agents/base.py`

```python
class Agent(Protocol):
    id: str                 # "DiscoveryAgent" — one spelling, used as the grant key
    system_prompt: str
    def grant(self) -> set[str]: ...
    def invoke(self, ctx: InvocationContext) -> AgentResult: ...
    def recover(self, err: ErrorInfo) -> RecoveryDecision: ...
```

Register: Orchestrator, Discovery (real), Planning (stub), Delivery (stub), Guidance subagent,
Research subagent. **Use one spelling of each agent id everywhere** — it is the grant table key.

### Global workflow — `ppa/workflow/transitions.yaml`

```
DISCOVERY --validate_discovery_state()--> DISCOVERY_VALIDATED --> PLANNING (v2 stub)
   ^  |  fail                                                        |
   |  +--> DISCOVERY                                                 v
   |                                                            PLAN_REVIEW
   |                                                                 | explicit user approval
   |                                                                 v
   |                                                            PLAN_APPROVED --> DELIVERY --> COMPLETE
   |
   +-- CHANGE_REQUESTED, reachable from EVERY state above --> impact analysis
                                                          --> rewind to earliest affected state
```

v1 runs `DISCOVERY → DISCOVERY_VALIDATED` and stops. Advancing returns NOT_IMPLEMENTED from the
Planning stub.

### Discovery-internal modes

`INTAKE → CLARIFY ⇄ GUIDANCE → RESEARCH → REVIEW → READY`, with CHANGE reachable from all.
Owned by the Discovery Agent, distinct from the global machine.

## Files touched

```
ppa/agents/base.py  ppa/agents/{discovery,planning,delivery}.py
ppa/agents/registry.py  (extend)
ppa/workflow/transitions.yaml  ppa/workflow/machine.py
tests/test_agents/test_registry.py
tests/test_agents/test_transitions.py
```

## Done when

- [x] All six agents/subagents register and declare grants
- [x] Agent ids use one spelling throughout — grep for variants and assert
- [x] The transition table is **data**; no workflow conditionals in Python
- [x] An illegal transition is rejected naming the rule that blocked it
- [x] `CHANGE_REQUESTED` is reachable from every state
- [x] Planning and Delivery stubs return structured NOT_IMPLEMENTED

## Build record

`ppa/agents/base.py` defines the `Agent` protocol (structural, `typing.Protocol`) plus `BaseAgent`
(concrete base every real agent inherits — `grant()` reads `ppa.agents.registry.GRANTS` directly,
never a second copy), `AgentResult`/`AgentResultStatus` (the seven outcomes §2.11 step 9
classifies into) and `RecoveryDecision`/`RecoveryActionKind` (what `Agent.recover()` returns — local
recovery, §2.14, distinct from a tool's own `RecoveryAction`). `ppa/agents/{discovery,planning,
delivery}.py` and `ppa/agents/subagents/{guidance,research}.py` each declare one real `Agent`
subclass; `ppa/agents/registry.py` gained an `OrchestratorAgent` (no dedicated file — nothing
invokes it the way it invokes the other five) and an `AGENTS: dict[str, BaseAgent]` mapping every
`GRANTS` key to a live instance, plus `agent_for()`.

**Corrected this task's own pseudocode**: `Agent.id` is `"discovery"` (the actual, already-shipped
`GRANTS` key, T14), not `"DiscoveryAgent"` as the task's worked example showed — logged as decision
#27, `blockers.md`, and enforced by a source-grep test (`test_source_files_declare_exactly_the_
registry_ids_no_variants`) so a future stray spelling fails the suite, not a code review.

**Found and fixed two real circular-import bugs while wiring this in** (`ppa.agents.base` <->
`ppa.agents.registry` <-> `ppa.tools.dispatch`, in both directions depending on which module a
caller imports first): `InvocationContext` is now a `TYPE_CHECKING`-only import everywhere it's
used purely as a type hint (six files), and `BaseAgent.grant()` imports `grant_for` inside the
method body rather than at module level, since `ppa.agents.registry` itself imports every concrete
`Agent` subclass of `BaseAgent`. Verified all three entry-point orderings (`ppa.agents.base` first,
`ppa.tools.dispatch` first, `ppa.agents.registry` first) resolve cleanly.

`ppa/workflow/transitions.yaml` + `ppa/workflow/machine.py`: the global state machine (§2.5) as
pure data plus a query layer (`legal_targets`, `condition_for`, `validate_transition`, `check` — the
last returning a `ToolResult` tagged `validation_layer_failed="workflow"`, consistent with T19's own
taxonomy) and `is_reachable_from_every_state`, used generically rather than hard-coding the
`CHANGE_REQUESTED` check. All eight states (including `PLANNING`/`PLAN_REVIEW`/`PLAN_APPROVED`/
`DELIVERY`/`COMPLETE`, unreachable from v1's own `DISCOVERY -> DISCOVERY_VALIDATED` walk in
practice) are declared now so the machine and `CHANGE_REQUESTED`'s reachability are provably
correct end to end before Planning/Delivery are real — the same boundary-first discipline T18
already applied to their tool stubs.

Tests: `tests/test_agents/test_registry.py` + `tests/test_agents/test_transitions.py`, 30 new tests.
Full suite re-run: **648 passed, 1 skipped** (618 baseline + 30).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_agents/`
3. Commit: `git add -A && git commit -m "T20: Agent protocol and workflow state machine"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t20_*.md completed_tasks\
   bash:     mv tasks/t20_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T20` on the board.
