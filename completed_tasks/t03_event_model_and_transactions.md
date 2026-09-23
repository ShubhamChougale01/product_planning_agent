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

Enumerate them explicitly. Every state change the system can make must map to exactly one. Write
the list out and check it against T02's entities:

`project.created` · `requirement.created|revised|confirmed|rejected|superseded` ·
`assumption.created|confirmed|rejected|modified` · `decision.opened|deferred|decided` ·
`unknown.recorded|classified|resolved|converted` · `question.asked` · `answer.recorded` ·
`research.recorded` · `coverage.recomputed` · `approval.granted|revoked` ·
`txn.begin|commit|abort` · `anomaly.loop_cap_reached` · `user.forced_ready`

**Amended during the build (2026-09-23):** checking this list against `ppa/ledger/transitions.py`
found it under-covers `TRANSITIONS` by four statuses — `Assumption` and `Decision` can both reach
`SUPERSEDED`, and `QuestionAnswer`/`ResearchFinding` can both reach `REPLACED` (decision #7), but
none of those four transitions had a designated event type above. Added `assumption.superseded`,
`decision.superseded`, `question.replaced`, `research.replaced` to close the gap — see
`blockers.md` for the full note. `Risk` intentionally gets none: T02 declared it "not written in
v1," so it has no reachable status yet.

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

- [x] Every state change in T02's entity set maps to exactly one event type — enumerate and verify
- [x] `reason` is required and rejects empty strings
- [x] Timestamps are timezone-aware; naive datetimes are rejected
- [x] `txn.begin` / `txn.commit` / `txn.abort` exist and carry `txn_id`
- [x] An event can be serialized to a single NDJSON line and parsed back identically

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/`
3. Commit: `git add -A && git commit -m "T03: Event model and transaction envelope"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t03_*.md completed_tasks\
   bash:     mv tasks/t03_*.md completed_tasks/
   ```

---

## Build record (completed 2026-09-23)

### A stub-labeling mismatch, caught before it cost anything

T01's scaffold left `ppa/ledger/events.py` with a docstring reading "Not implemented yet — filled
in by T06." Checking T06's own task file before starting found that T06 actually names
`ppa/ledger/store.py` for the append/lock/fsync mechanism — `events.py` was free, and is exactly
where this task's own "Files touched" section says the envelope belongs. No real conflict, same
root cause as blocker #2 (T01 guessed a filename-to-task mapping instead of checking the
downstream task file that actually names it). Logged in `blockers.md`, not silently fixed.

### The four added event types

Enumerating T02's `TRANSITIONS` matrix status-by-status against the task's own event-type list
found four reachable statuses with no designated event type: `Assumption.SUPERSEDED`,
`Decision.SUPERSEDED`, `QuestionAnswer.REPLACED`, `ResearchFinding.REPLACED`. Added
`assumption.superseded`, `decision.superseded`, `question.replaced`, `research.replaced` to close
the gap — see the amendment above and `blockers.md`. `Risk` was deliberately left with zero event
types: T02 declared it "not written in v1," so it has no reachable status yet; revisit when
Planning lands in v2.

The mapping used to prove coverage (`STATUS_EVENT_MAP` in `tests/test_ledger/test_events.py`) is
tested directly against `TRANSITIONS`, not just eyeballed — `test_every_reachable_status_has_a_
designated_event_type` fails if a future entity/status is added to `transitions.py` without a
matching event type here.

### What exists now

```
ppa/ledger/events.py              # EventType (32 members), Event envelope
tests/test_ledger/test_events.py  # 26 tests
```

### Verification

```
$ .venv/Scripts/python.exe -m pytest tests/test_ledger/test_events.py -> 26 passed
$ .venv/Scripts/python.exe -m pytest                                  -> 143 passed
```

No open blockers. No bugs found. The stub-mislabeling note above is informational, not a defect —
it cost zero time because it was checked before building rather than after.

### Notes for whoever picks up T06

- `ppa/ledger/store.py` is genuinely empty and waiting — build `append_event()` there, importing
  `Event`/`EventType` from `ppa/ledger/events.py`.
- `ppa/ledger/secrets.py` already carries the correct T06 stub docstring; no mismatch there.
- Every `Event` must be constructed with a non-empty `reason` and a timezone-aware `ts` — both are
  enforced by Pydantic validators, so a bad call raises at construction, not at write time.

5. Open `tasks/README.md` and tick `T03` on the board.
