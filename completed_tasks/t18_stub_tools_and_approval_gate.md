# T18 — Stub tools and the approval gate

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.1, §2.19.2, S5.7, S5.9 |

## Prerequisites

- [x] **T16**

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

- [x] All ten stub tools are registered with complete ToolSpecs
- [x] Stubs return NOT_IMPLEMENTED with `INFORM_USER`, not an exception
- [x] `manage_linear_issue` returns BUSINESS when `plan.status != APPROVED` — **tested now**
- [x] Creation with **no** approval returns BUSINESS and creates nothing
- [x] Creation with an **expired** approval returns BUSINESS
- [x] Creation where `scope_hash` no longer matches returns BUSINESS
- [x] `approval.granted` and `approval.revoked` events are emitted and *folded* — **corrected wording,
      see decision #25 in `blockers.md`.** They are not "materialized" in T07's sense (a file under
      `entities/`): they carry no `entity_id` and are not one of T02's seven locked entity types, so
      extending `ppa/ledger/materialize.py`'s `ENTITY_TYPES` table for an eighth pseudo-entity was
      out of this task's scope. `ppa.tools.approval.current_approval` folds them itself — same
      "latest write wins" principle, scoped to event `type` instead of `entity_id`.

## Build record

`ppa/tools/planning_tools.py` and `ppa/tools/delivery_tools.py` each declare their four non-shared
tools (`read_planning_state` was already registered by T15 and granted to both) with full
`ToolSpec`s and real grants. Seven of the eight are pure `NOT_IMPLEMENTED` stubs — same body shape
in both files (`_not_implemented(tool_name)`), unconditional regardless of input, rendered with the
task's own quoted message for Planning and an analogous one for Delivery.

`manage_linear_issue` is the one real guardrail: `@requires_approval` (from the new
`ppa/tools/approval.py`) runs first, checking `current_approval` against the call's `scope_hash`;
the body then separately checks `plan_status == "APPROVED"`. Both checks are independent BUSINESS
rejections, both tested with the other precondition satisfied so neither test result depends on
which check happens to run first. No external Linear call is made — `created_issue_ids` are stub
ids (`LINEAR-STUB-<story_id>`); what's real is that nothing gets even that far without a valid,
unexpired, exactly-matching approval and an approved plan.

`ppa/tools/approval.py` has no MCP-registered tool of its own — `grant_approval`/`revoke_approval`
are plain functions for a human-facing surface (T31's CLI, or an escalation flow) to call, never
something an agent invokes; check `ppa/agents/registry.py::GRANTS` for any agent and note no grant
names them. `current_approval` folds `approval.granted`/`approval.revoked` events itself, since
neither is one of T02's seven locked entity types (see the corrected Done-when box above and
decision #25, `blockers.md`).

Tests: `tests/test_tools/test_stubs.py` (11 tests) + `tests/test_permissions/test_approval.py`
(15 tests) = 26 new tests. Full suite re-run: **600 passed** (574 baseline + 26).

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
