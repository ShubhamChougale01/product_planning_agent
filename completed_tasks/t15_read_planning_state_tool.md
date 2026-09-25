# T15 — read_planning_state — the consolidated reader

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.8, S5.4 |

## Prerequisites

- [x] **T09**
- [x] **T10**
- [x] **T11**
- [x] **T12**
- [x] **T14**

## Why this task exists

One read tool instead of six. All reads share a permission profile, have no side effects and fail
the same way, so consolidating them is a real simplification rather than hiding a selection
problem inside a parameter — which is the opposite of what merging the writers would do.

## What to build

### Tool — `ppa/tools/discovery_tools.py`

```
read_planning_state(scope, **kwargs) -> ToolResult

scope:
  "digest"      full compact snapshot          (T09)
  "entity"      one entity by id, or a filtered list
  "history"     version trail for one entity
  "coverage"    area states + critical fraction (T10)
  "open_items"  sorted, dated, owner-attributed (T12)
  "readiness"   gate result + blocker list      (T10)
  "impact"      traversal from one entity       (T11)
```

Thin wrapper. **No logic** — every scope delegates to an engine built in Phase A.

### Guard rails

- `scope="entity"` **requires** a filter and enforces a result cap. It must be impossible to
  return the whole ledger — that is what `digest` is for.
- `readiness` returns the blocker list, not just a boolean. The agent needs to explain itself.
- Results are data, never prose. Narration is the model's job, at the point of use.

## Files touched

```
ppa/tools/discovery_tools.py
tests/test_tools/test_read_state.py
```

## Done when

- [x] All seven scopes return well-formed `ToolResult` objects
- [x] `scope=\"entity\"` without a filter is rejected as VALIDATION
- [x] No scope can return the entire ledger — verify with a 200-entity fixture
- [x] Each scope delegates to its engine; the tool body is under 20 lines per scope
- [x] `readiness` returns blockers, not just a boolean
- [x] The ToolSpec has all thirteen fields and distinguishes itself from the write tools

## Build record

Filled in `ppa/tools/discovery_tools.py` (previously a stub shared across T15-T17): `read_planning_
state(scope, project, **kwargs)` as the pure, directly-testable router; `_read_planning_state_handler`
as the SDK-facing async adapter that resolves a `Project` from `project_slug` before delegating;
`READ_PLANNING_STATE_SPEC` registered at import time, granted to all five agents that read state
(discovery, guidance, research, planning, delivery — everyone but the orchestrator, per §2.8's table).

Each of the seven scopes is a small function that calls exactly one Phase-A engine
(`ppa/ledger/digest.py`, `ppa/engines/{coverage,readiness,open_items,impact}.py`) and wraps its
result in a `ToolResult` — no scope computes anything itself. `scope="entity"` is the one scope that
could otherwise return the whole ledger, so it's the one with a mandatory filter and a hard 20-row cap
regardless of what `limit` a caller passes.

**Found and fixed a real cross-task-file bug while building this** (logged as bug #4): T13/T14's test
files each had an autouse fixture that called `clear_registry()` — since Python only runs a module's
top-level `register()` once, on first import, any test file's bare clear would have permanently erased
`discovery_tools.py`'s real `read_planning_state` registration for the rest of the test session, the
first time this task's own module got imported. Added `ppa/tools/registry.py::snapshot()`/`restore()`
and updated all four registry-clearing fixtures (T13's two, T14's one, this task's own) to use them
instead of a bare clear.

**Also reorganized `blockers.md`**: decisions #15-23, logged across T08-T15, had drifted from the
file's own stated rule ("Taken" without "needs confirmation" belongs in §4, not §2) — several were
sitting in §2 that should have moved straight to §4 on being logged. Corrected without changing any
decision's content, reasoning, or number.

Tests: `tests/test_tools/test_read_state.py`, 27 tests. Full suite re-run: **518 passed**
(491 after T14, +27).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_tools/`
3. Commit: `git add -A && git commit -m "T15: read_planning_state — the consolidated reader"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t15_*.md completed_tasks\
   bash:     mv tasks/t15_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T15` on the board.
