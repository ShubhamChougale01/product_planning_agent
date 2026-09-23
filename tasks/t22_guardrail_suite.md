# T22 — Guardrail suite

| | |
|---|---|
| **Phase** | C · Orchestration and guardrails |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.13, §2.19, S6.5 |

## Prerequisites

- [ ] **T21**

## Why this task exists

Every "must not" in the design becomes a passing test here, before any agent prompt exists. If a
guardrail is only enforced by prompt text, it is not enforced. This is the task that proves the
boundaries hold.

## What to build

### Every rule, as a test

```
plan.status != APPROVED           -> manage_linear_issue     REJECT (BUSINESS)
any blocking Unknown still OPEN   -> advance to PLANNING     REJECT, route to Discovery
critical assumption unconfirmed   -> plan approval           BLOCK
caller == DiscoveryAgent          -> manage_linear_issue     REJECT (PERMISSION)
caller == DeliveryAgent           -> manage_requirement      REJECT (PERMISSION)
caller == PlanningAgent           -> manage_linear_issue     REJECT (PERMISSION)
no approval / expired / stale hash-> manage_linear_issue     REJECT (BUSINESS)
DISCOVERY state                   -> generate_story          REJECT
```

### Agent prohibitions, from §2.4

- Discovery must not create a plan, generate stories, or touch Linear
- Planning must not create Linear issues, invent requirements, or promote an assumption to
  CONFIRMED without an explicit user confirmation event
- Delivery must not modify approved requirements, or generate work from a non-APPROVED plan
- Orchestrator must not hold domain tools or write requirements

Each of these is a test. The Linear-before-approval case must pass **in v1, against stubs** —
that is the whole point of building the boundaries early.

## Files touched

```
tests/test_permissions/test_guardrails.py
tests/test_agents/test_prohibitions.py
```

## Done when

- [ ] Every rule in the table above has a passing test
- [ ] Every agent prohibition in §2.4 has a passing test
- [ ] Linear-before-approval passes in v1 against the stub
- [ ] The Orchestrator holds zero domain tools — assert against its grant
- [ ] Each rejection names the rule that blocked it, not a generic message
- [ ] The whole suite runs in under 5 seconds with no model calls

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_permissions/ tests/test_agents/`
3. Commit: `git add -A && git commit -m "T22: Guardrail suite"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t22_*.md completed_tasks\
   bash:     mv tasks/t22_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T22` on the board.
