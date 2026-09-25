# T19 — Validation layer wiring

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.13, S5.8 |

## Prerequisites

- [x] **T14**
- [x] **T16**

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

- [x] Each layer has a test that fails **at that layer and no earlier**
- [x] `validation_layer_failed` appears in the audit record for every rejection
- [x] A call that would fail at multiple layers reports the earliest one
- [x] Bypassing the tool layer cannot mutate state — attempt a direct file write in a test and assert the digest is unchanged
- [x] Layer numbering in code comments matches §2.13 exactly

## Build record

Filled all five `ppa/validation/*.py` stubs with real, independently-testable logic: `permission.
check` (wraps `ppa.agents.registry.grant_for`), `schema.check` (generic, `ToolSpec`-driven —
required fields plus any `"one of: a, b, c"` format string), `workflow.check` (a table of which
global workflow states a tool is legal in, defaulting open for anything the table doesn't name),
`semantic.py` (a small registry so a tool's rule is declared once, next to the tool that owns it,
and still independently discoverable/testable here), `consistency.check_transition` (wraps
`ppa.ledger.transitions.validate_transition`, converting `IllegalTransition` into the same
`ToolResult` shape every other layer returns).

`ppa/tools/hooks.py::pre_tool_use` runs layers 1-3 in order and returns the first failure — proven
by two tests where a call fails at two layers at once and only the earlier one is reported.
Layers 4-5 stay where §2.13 already puts them (the tool body, since semantic/consistency checks may
need to load related entities) — `ppa.tools.discovery_tools._generic_transition` (T16) now calls
`ppa.validation.consistency.check_transition` directly instead of importing `ppa.ledger.transitions`
itself, and registers its one semantic rule into `ppa.validation.semantic` at import time, so both
layers are genuinely wired into the one writer that has them, not just declared in parallel.

**`validation_layer_failed` is inferred, not hand-tagged at every call site.** `ppa/validation/
__init__.py::infer_validation_layer` maps an `ErrorInfo`'s category/code to a layer name once;
`discovery_tools.py`'s `_audit_write`, `interaction.py`'s batch-rejection audit call, and
`delivery_tools.py`'s `_audit_linear` each call it at their one existing audit point instead of
threading a new `layer=` parameter through ~30 existing `_error(...)` call sites. Found and fixed a
real gap while wiring this in: `ppa/tools/approval.py`'s `@requires_approval` decorator rejected
without ever auditing (its rejection short-circuits before the wrapped function's own body, which is
where all the auditing lived) — added an audit call directly in the decorator's own rejection path,
correctly reporting `validation_layer_failed=None` since the approval gate is a sixth, separate gate
(§2.19.2), not one of the five layers.

**`ppa/tools/dispatch.py` is deliberately untouched** — not in this task's own "Files touched" list,
and T14's existing tests (`tests/test_permissions/test_grants.py`) assert today's dispatcher
behavior with fake handlers that don't return real `ToolResult` JSON; changing dispatch.py's
success-wrapping to trust the handler's actual result would break those tests without being asked
for here. `pre_tool_use` is complete and tested standalone; wiring it into `dispatch.py`'s own
marked insertion point is left for whichever task next touches it. Logged as decision #26 in
`blockers.md`.

Tests: `tests/test_validation/test_layer_order.py`, 18 tests — including coverage for the
approval-gate audit fix (`test_validation_layer_failed_is_none_for_a_permission_style_approval_
rejection`), verified against T18's existing `tests/test_permissions/test_approval.py` suite too
(unchanged, still 15 passing). Full suite re-run:
**618 passed** (600 baseline + 18).

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
