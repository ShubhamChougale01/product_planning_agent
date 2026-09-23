# T32 — Transactions, retry, recovery and escalation

| | |
|---|---|
| **Phase** | F · Resilience and validation |
| **Estimate** | 1.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.14, §2.15, S11.1–S11.4 |

## Prerequisites

- [ ] **T21**

## Why this task exists

Failures are inevitable; silent corruption is not acceptable. The objective is not "never fail"
— it is that failures are observable, classifiable, recoverable where possible, and incapable of
leaving the ledger in an invalid state.

## What to build

### Transactions

Event sourcing makes this cheap: **validation happens before append, and the append is the
commit.** A rejected write leaves nothing to roll back.

```
txn.begin   {txn_id, checkpoint_version}
  ... events carrying txn_id ...
txn.commit  {txn_id}     <- materializer ignores any txn without this
```

On failure: no commit; write `txn.abort` with the reason and any partial results.

### Bounded retry — `ppa/recovery/retry.py`

Budget of **3 per operation**, not global. Exponential backoff honouring `retry_after_ms`.
Only `TRANSIENT` is retried. Exhaustion produces:

```json
{ "status": "PARTIAL_FAILURE", "attempted": 5, "successful": 3, "failed": 2,
  "error_category": "TRANSIENT", "partial_results": [...],
  "next_action": "ESCALATE_TO_ORCHESTRATOR" }
```

Never a bare failure.

### Local recovery first

A Discovery research timeout is retried **inside Discovery**. The Orchestrator is involved only
when the agent cannot resolve it locally, and the propagated result says what was attempted.

### Escalation — `ppa/orchestrator/escalation.py`

Triggered by: a critical requirement that cannot be determined, conflicting user decisions, a
business-rule conflict, a permission conflict, repeated tool failure past budget, plan approval,
or a HIGH-impact assumption awaiting confirmation.

Every escalation states, **in this order**: what happened · what is missing · what was attempted ·
what the options are · what decision is needed.

**An escalation that does not end in a concrete question is a bug.** The user should never have
to ask "so what do you want from me?"

## Files touched

```
ppa/recovery/{transaction,retry}.py
ppa/orchestrator/escalation.py
tests/test_recovery/
```

## Done when

- [ ] A crash injected mid-transaction leaves the ledger at its pre-transaction state
- [ ] The aborted transaction records what was attempted, via `txn.abort`
- [ ] A flapping tool succeeds within the budget of 3
- [ ] An always-failing tool exhausts and returns `PARTIAL_FAILURE` with attempt counts and partial results
- [ ] Only `TRANSIENT` errors are retried — `VALIDATION` is never resent identically
- [ ] A subagent retries locally before propagating; the Orchestrator receives partials, not a bare failure
- [ ] **Every** escalation path ends in a concrete question — a test asserts no escalation renders without one

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_recovery/`
3. Commit: `git add -A && git commit -m "T32: Transactions, retry, recovery and escalation"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t32_*.md completed_tasks\
   bash:     mv tasks/t32_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T32` on the board.
