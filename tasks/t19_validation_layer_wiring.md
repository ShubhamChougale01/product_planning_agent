# T19 — Validation layer wiring

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.13, S5.8 |

## Prerequisites

- [ ] **T14**
- [ ] **T16**

## Why this task exists

Five layers already exist scattered across the writers. This task makes the order explicit,
uniform and observable, so that when something is rejected you know which layer rejected it and
why — both in tests and in the audit log.

## What to build

### Order — and it matters

| # | Layer | Where | Rejects |
|---|---|---|---|
| 1 | **Permission** | dispatcher, pre-body | agent not granted this tool |
| 2 | Schema | Pydantic | types, enums, formats, required fields |
| 3 | Workflow | orchestrator + tool guard | action illegal in current state |
| 4 | Semantic | tool body | CONFIRMED requirement with an UNKNOWN target user |
| 5 | Consistency | store, pre-append | version mismatch, dangling refs, illegal transition |

Permission first: cheapest check, and it must not leak schema details about a tool the caller
may not use. Workflow before semantic: workflow is a table lookup, semantic may need to load
related entities.

### Observability

Every rejection records `validation_layer_failed` in the audit log. Without it, debugging a
rejected write means guessing.

### Hook wiring

`PreToolUse` → layers 1–3. `PostToolUse` → event append, materialize, digest, audit.

## Files touched

```
ppa/validation/{permission,schema,workflow,semantic,consistency}.py
ppa/tools/hooks.py
tests/test_validation/test_layer_order.py
```

## Done when

- [ ] Each layer has a test that fails **at that layer and no earlier**
- [ ] `validation_layer_failed` appears in the audit record for every rejection
- [ ] A call that would fail at multiple layers reports the earliest one
- [ ] Bypassing the tool layer cannot mutate state — attempt a direct file write in a test and assert the digest is unchanged
- [ ] Layer numbering in code comments matches §2.13 exactly

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_validation/`
3. Commit: `git add -A && git commit -m "T19: Validation layer wiring"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t19_*.md completed_tasks\
   bash:     mv tasks/t19_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T19` on the board.
