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

- [ ] Constructing `ErrorInfo` without `recommended_action` raises
- [ ] A category/action pair outside the table above raises
- [ ] `TRANSIENT` is the only category with `is_retryable=True`
- [ ] `success=True, result_count=0` is expressible and is not an error
- [ ] `degraded=True` is expressible alongside `success=True`
- [ ] A test asserts the full mapping table exactly as written above

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
