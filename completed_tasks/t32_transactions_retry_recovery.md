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

- [x] A crash injected mid-transaction leaves the ledger at its pre-transaction state
- [x] The aborted transaction records what was attempted, via `txn.abort`
- [x] A flapping tool succeeds within the budget of 3
- [x] An always-failing tool exhausts and returns `PARTIAL_FAILURE` with attempt counts and partial results
- [x] Only `TRANSIENT` errors are retried — `VALIDATION` is never resent identically
- [x] A subagent retries locally before propagating; the Orchestrator receives partials, not a bare failure
- [x] **Every** escalation path ends in a concrete question — a test asserts no escalation renders without one

## Build record

**Transactions were already cheap, by construction, before this task** (the task's own opening
line): `ppa.orchestrator.loop` (T21) already opens one `txn.begin`/`txn.commit` pair per outer-loop
iteration, and `ppa.ledger.materialize._effective_events` (T07) already excludes any `txn_id` that
never reached a matching `txn.commit` before folding entity state. `ppa/recovery/transaction.py`
makes that guarantee independently checkable rather than trusted by construction alone:
`checkpoint`/`verify_rolled_back` capture materialized state before a transaction and prove it is
unchanged after a crash (events written, no commit) — proven against a real project, injecting a
`REQUIREMENT_CREATED` event under an open `txn_id` with no matching `txn.commit`, then a second
test proving the same check reports `False` once a matching `txn.commit` really lands (so the
check is meaningful, not vacuously true). `txn.abort`'s own "records what was attempted" half
needed no new code at all — `ppa.orchestrator.loop`'s existing `_abort_txn` calls already carry the
agent's own failure summary in `reason`; this task's suite is the first to assert that directly
(`test_every_aborted_attempt_records_what_was_attempted`, reusing T21's own `_FixtureAgent`
pattern).

`ppa/recovery/retry.py` — `retry_operation` retries a single operation up to a budget of 3
(`DEFAULT_RETRY_BUDGET`, matching `ppa.orchestrator.loop`'s own constant), honoring `retry_after_ms`
when a failure states one, exponential fallback otherwise; only `ErrorCategory.TRANSIENT` is ever
retried — every other category's fixed `is_retryable=False` (`ppa/results/categories.py`, T05)
means this module simply never resends them. `retry_batch` folds a sequence of operations into the
task's own worked `PARTIAL_FAILURE` JSON shape exactly (`status`/`attempted`/`successful`/`failed`/
`error_category`/`partial_results`/`next_action`), `attempted == successful + failed` always.

**"Local recovery first" and "the Orchestrator receives partials, not a bare failure"** are proven
generically (`tests/test_recovery/test_local_recovery.py`) rather than by rewiring a real
production subagent — `ppa/agents/subagents/research.py` (T29) is out of this task's own "Files
touched" scope, and `AgentResult` (T20) already carries exactly `retry_batch`'s own fields
(`attempted`/`successful`/`failed`/`partial_results`/`next_action`), so the wiring a real subagent
would do is demonstrated against a stand-in "local turn" function instead — the same shape any real
subagent's own batching loop (T29's `run_research_session`, for instance) would use, without this
task widening its own file scope to actually modify one.

`ppa/orchestrator/escalation.py` — `Escalation` structurally enforces this task's own instruction:
`question` and every other narrative field is required and non-empty, `options` must carry at least
one entry — a Pydantic `ValidationError`, not a silent gap, if a caller tries to construct an
escalation missing any of the five parts. `render_escalation` renders What happened / What is
missing / What was attempted / Options / What I need from you, always in that order. All seven
named triggers (`EscalationTrigger`) are declared verbatim from the task's own list; parametrized
tests build one real escalation per trigger and assert every rendering ends in its own concrete
question.

Tests: `tests/test_recovery/` — 25 tests (`test_retry.py`, `test_transaction.py`,
`test_escalation.py`, `test_local_recovery.py`), all zero-cost, no model involved (matching this
task's own "Needs a model: No"). Full suite re-run: 878 passed (853 baseline after T31 + 25 new), 1
skipped.

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
