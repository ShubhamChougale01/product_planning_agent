# T05 — Result envelope and error taxonomy

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.12, S1.7 |

## Prerequisites

- [ ] **T02**

## Why this task exists

Every tool written from T13 onward speaks this language. Defining it before the first tool means
no tool ever returns a bare string, and recovery logic has something to branch on. The critical
design point: `recommended_action` is the contract, `is_retryable` is advisory.

## What to build

### Envelope — `ppa/results/envelope.py`

```python
class ToolResult(BaseModel):
    success: bool
    degraded: bool = False        # succeeded with reduced capability
    result_count: int = 0
    data: Any | None = None
    error: ErrorInfo | None = None

class ErrorInfo(BaseModel):
    category: ErrorCategory
    code: str                     # LEDGER_WRITE_TIMEOUT
    is_retryable: bool
    retry_after_ms: int | None
    description: str
    recommended_action: RecoveryAction   # required, never None
    context: dict = {}
```

### The five categories and their fixed mapping

| Category | `is_retryable` | `recommended_action` |
|---|---|---|
| `TRANSIENT` | true | `RETRY_SAME` |
| `VALIDATION` | false | `CORRECT_AND_RETRY` |
| `BUSINESS` | false | `CHANGE_WORKFLOW` |
| `PERMISSION` | false | `ABORT_AND_ROUTE` |
| `NOT_IMPLEMENTED` | false | `INFORM_USER` |

Enforce the mapping in a validator — constructing an `ErrorInfo` that violates it must raise.

### Three states, not two

- **Success with data** — `success=True, result_count=N`
- **Success and empty** — `success=True, result_count=0`. A research query that ran and found
  nothing is **not** a failure. Never convert it to one; never retry it because it is empty.
- **Degraded success** — `success=True, degraded=True`. Ran without full capability, e.g.
  research with no web access. Honest caveat, not an error.

## Files touched

```
ppa/results/envelope.py
ppa/results/categories.py
tests/test_results/test_envelope.py
```

## Done when

- [x] Constructing `ErrorInfo` without `recommended_action` raises
- [x] A category/action pair outside the table above raises
- [x] `TRANSIENT` is the only category with `is_retryable=True`
- [x] `success=True, result_count=0` is expressible and is not an error
- [x] `degraded=True` is expressible alongside `success=True`
- [x] A test asserts the full mapping table exactly as written above

## Traps

Do not let `is_retryable=False` read as "give up" anywhere in the codebase or in any tool
description. It means only "do not resend this identical request". `recommended_action` is what
callers branch on.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_results/`
3. Commit: `git add -A && git commit -m "T05: Result envelope and error taxonomy"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t05_*.md completed_tasks\
   bash:     mv tasks/t05_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T05` on the board.

---

## Build record (completed 2026-09-24)

### One rule added beyond the Done-when list

`ToolResult` also enforces `success=True` ⇒ `error is None` and `success=False` ⇒ `error is not None`.
Not its own Done-when box, but a direct, mechanical consequence of §2.12's own JSON example and
the "three states, not two" description — an envelope with `success=False` and no `error` would
have nothing for recovery logic to branch on, which is exactly what this task exists to prevent.
No user confirmation needed for this one (unlike decisions #7/#11): it's implied by the spec
itself, not a genuine gap requiring a judgment call.

### No blockers, no bugs

Stub files (`ppa/results/envelope.py`, `ppa/results/categories.py`) were correctly labeled from
T01's scaffold — no naming mismatch this time. The category → action mapping in the task matched
DESIGN.md §2.12 exactly, so `CATEGORY_RULES` needed no gap-filling.

### What exists now

```
ppa/results/categories.py          # ErrorCategory, RecoveryAction, CATEGORY_RULES
ppa/results/envelope.py            # ErrorInfo, ToolResult
tests/test_results/test_envelope.py  # 26 tests
```

### Verification

```
$ .venv/Scripts/python.exe -m pytest tests/test_results/ -> 26 passed
$ .venv/Scripts/python.exe -m pytest                      -> 198 passed
```

### Notes for whoever picks up T06

- Every tool from T13 onward returns `ToolResult`, never a bare value or a raw exception.
- `is_retryable` is advisory; branch retry/recovery logic on `recommended_action`, not on
  `is_retryable` alone (the task's own trap warning — still true for every later task).
