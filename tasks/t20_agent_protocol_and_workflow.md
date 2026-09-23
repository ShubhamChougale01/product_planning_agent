# T20 — Agent protocol and workflow state machine

| | |
|---|---|
| **Phase** | C · Orchestration and guardrails |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.4, §2.5, S6.1–S6.2 |

## Prerequisites

- [ ] **T18**

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

- [ ] All six agents/subagents register and declare grants
- [ ] Agent ids use one spelling throughout — grep for variants and assert
- [ ] The transition table is **data**; no workflow conditionals in Python
- [ ] An illegal transition is rejected naming the rule that blocked it
- [ ] `CHANGE_REQUESTED` is reachable from every state
- [ ] Planning and Delivery stubs return structured NOT_IMPLEMENTED

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
