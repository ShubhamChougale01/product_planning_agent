# T22 — Guardrail suite

| | |
|---|---|
| **Phase** | C · Orchestration and guardrails |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.13, §2.19, S6.5 |

## Prerequisites

- [x] **T21**

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

- [x] Every rule in the table above has a passing test
- [x] Every agent prohibition in §2.4 has a passing test
- [x] Linear-before-approval passes in v1 against the stub
- [x] The Orchestrator holds zero domain tools — assert against its grant
- [x] Each rejection names the rule that blocked it, not a generic message
- [x] The whole suite runs in under 5 seconds with no model calls

## Build record

`tests/test_permissions/test_guardrails.py` — one test per row in this task's own table, each
named after the rule it proves rather than the mechanism underneath. Every rule was already real
(T14 permission, T18 approval gate, T19 workflow layer, T21 preconditions, T10 readiness) — this
file's job is to be the single place a reader checks "does every guardrail in the design doc have
proof," not to duplicate `test_approval.py`'s own already-thorough mechanism tests. "Critical
assumption unconfirmed -> plan approval BLOCK" is tested against `check_readiness`'s own
`unconfirmed_high_assumption` condition directly — "plan approval" itself is T30's feature, not
yet buildable (decision #19), but the condition that will gate it is real and tested today.

`tests/test_agents/test_prohibitions.py` — one test per §2.4 prohibition, checked directly against
`ppa.agents.registry.GRANTS`, plus the Orchestrator's own zero-domain-tools box (`DOMAIN_TOOLS`,
every real tool any other agent holds, intersected against `GRANTS["orchestrator"]`). "Delivery
must not... generate work from a non-APPROVED plan" is the one prohibition that is not a grant gap
(Delivery *is* granted `generate_story`, correctly) — it is `ppa.validation.workflow`'s own
`DISCOVERY`-state rejection, cross-referenced rather than re-derived.

**Decision #29** (`blockers.md`): the guardrail suite's fixture `Project` is built directly, never
through `ppa.ledger.project.create_project` — none of the eight rules touch git, and
`create_project`'s own `git init`/two `commit()` calls (subprocess spawns) pushed the first version
of this suite to 9.07s against Windows, blowing the task's own "under 5 seconds" box. Rebuilt on a
bare `Project(...)` over an un-initialized `tmp_path`: 0.69s.

Tests: 21 new (`test_guardrails.py` + `test_prohibitions.py`). Full suite re-run: **698 passed, 1
skipped** (677 baseline + 21).

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
