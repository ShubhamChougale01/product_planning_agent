# T15 — read_planning_state — the consolidated reader

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.8, S5.4 |

## Prerequisites

- [ ] **T09**
- [ ] **T10**
- [ ] **T11**
- [ ] **T12**
- [ ] **T14**

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

- [ ] All seven scopes return well-formed `ToolResult` objects
- [ ] `scope=\"entity\"` without a filter is rejected as VALIDATION
- [ ] No scope can return the entire ledger — verify with a 200-entity fixture
- [ ] Each scope delegates to its engine; the tool body is under 20 lines per scope
- [ ] `readiness` returns blockers, not just a boolean
- [ ] The ToolSpec has all thirteen fields and distinguishes itself from the write tools

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
