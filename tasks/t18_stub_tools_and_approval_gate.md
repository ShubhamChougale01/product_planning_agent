# T18 — Stub tools and the approval gate

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.1, §2.19.2, S5.7, S5.9 |

## Prerequisites

- [ ] **T16**

## Why this task exists

Planning and Delivery are v2/v3, but their **boundaries** are built now. The expensive refactor
is never "add a feature", it is "add a boundary" — boundaries retrofitted later leak. This task
makes `manage_linear_issue` exist, permission-gated and approval-gated, and proves the guardrails
work before Linear is real.

## What to build

### Stub tools

Declare Planning's five and Delivery's five in the registry with **full ToolSpecs**. Bodies
return `NOT_IMPLEMENTED` with `recommended_action=INFORM_USER`, rendered as:

> Planning is v2. Discovery is validated and the ledger is ready for it.

A stub is not a `pass` — it is a real registration with real grants and real guardrails.

### Approval gate — `ppa/tools/approval.py`

Permission asks *may this agent*. Approval asks *does the user want it*. Different questions.

An action needs an approval gate when it is **external**, **irreversible** or **bulk**. Creating
Linear issues is all three.

```
1 DRY RUN   render exactly what would be created. Nothing leaves the system.
2 PRESENT   full preview, plus a diff if an issue already exists
3 APPROVE   one approval for the batch ->
            approval.granted{scope_hash, story_ids[], granted_by, granted_at, expires_at}
4 EXECUTE   the tool verifies the approval covers THIS scope_hash
5 RECORD    per-issue results; partial failure preserved, never silently retried into duplicates
```

**`scope_hash` is what makes this a gate rather than ceremony.** It is computed over the exact
story set. Edit, add or remove a story and the hash changes, the approval no longer covers it,
and re-approval is required. An approval that survives arbitrary changes to what it approved is
not an approval.

Batch, not per-issue: forty individual confirmations produce rubber-stamping, which is worse than
one considered decision made against a complete preview. Approvals expire — default 24h — so a
stale one cannot be replayed in a later session.

### Decorator

`@requires_approval(scope_fn)` — any external or irreversible tool must declare it.

## Files touched

```
ppa/tools/planning_tools.py
ppa/tools/delivery_tools.py
ppa/tools/approval.py
tests/test_tools/test_stubs.py
tests/test_permissions/test_approval.py
```

## Done when

- [ ] All ten stub tools are registered with complete ToolSpecs
- [ ] Stubs return NOT_IMPLEMENTED with `INFORM_USER`, not an exception
- [ ] `manage_linear_issue` returns BUSINESS when `plan.status != APPROVED` — **tested now**
- [ ] Creation with **no** approval returns BUSINESS and creates nothing
- [ ] Creation with an **expired** approval returns BUSINESS
- [ ] Creation where `scope_hash` no longer matches returns BUSINESS
- [ ] `approval.granted` and `approval.revoked` events are emitted and materialized

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_tools/ tests/test_permissions/`
3. Commit: `git add -A && git commit -m "T18: Stub tools and the approval gate"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t18_*.md completed_tasks\
   bash:     mv tasks/t18_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T18` on the board.
