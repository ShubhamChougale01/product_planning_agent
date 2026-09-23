# T03 — Event model and transaction envelope

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.8, §2.14, S1.3 |

## Prerequisites

- [ ] **T02**

## Why this task exists

The event log is the source of truth; entity files are a materialized view of it. Getting the
envelope right now means version history, change reasons, audit attribution and crash recovery
all fall out for free later. Getting it wrong means retrofitting all four.

## What to build

### Envelope

`ppa/ledger/events.py`:

```python
class Event(BaseModel):
    event_id: str             # EVT-000142, monotonic
    ts: datetime              # timezone-aware, always
    type: EventType
    entity_id: str | None
    actor_id: str
    actor_role: Literal["agent", "user"]
    agent_name: str | None    # DiscoveryAgent, GuidanceSubagent, ...
    workflow_state: str
    txn_id: str | None
    source: str               # "clarification_round_3"
    reason: str               # required, non-empty
    before: dict | None
    after: dict | None
    session_id: str
```

### Event types

Enumerate them explicitly — roughly 18. Every state change the system can make must map to
exactly one. Write the list out and check it against T02's entities:

`project.created` · `requirement.created|revised|confirmed|rejected|superseded` ·
`assumption.created|confirmed|rejected|modified` · `decision.opened|deferred|decided` ·
`unknown.recorded|classified|resolved|converted` · `question.asked` · `answer.recorded` ·
`research.recorded` · `coverage.recomputed` · `approval.granted|revoked` ·
`txn.begin|commit|abort` · `anomaly.loop_cap_reached` · `user.forced_ready`

### Transactions

`txn.begin{txn_id, checkpoint_version}` … events carrying `txn_id` … `txn.commit{txn_id}`.
A transaction without a commit is **ignored by the materializer** (T07). That is the whole
rollback mechanism — no undo needed, because nothing invalid is ever committed.

## Files touched

```
ppa/ledger/events.py
tests/test_ledger/test_events.py
```

## Done when

- [ ] Every state change in T02's entity set maps to exactly one event type — enumerate and verify
- [ ] `reason` is required and rejects empty strings
- [ ] Timestamps are timezone-aware; naive datetimes are rejected
- [ ] `txn.begin` / `txn.commit` / `txn.abort` exist and carry `txn_id`
- [ ] An event can be serialized to a single NDJSON line and parsed back identically

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/`
3. Commit: `git add -A && git commit -m "T03: Event model and transaction envelope"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t03_*.md completed_tasks\
   bash:     mv tasks/t03_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T03` on the board.
