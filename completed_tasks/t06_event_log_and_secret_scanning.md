# T06 — Event log with inbound secret scanning

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.14, §2.19.1, S2.1, S2.1b |

## Prerequisites

- [ ] **T03**

## Why this task exists

The append-only log is the foundation everything else materializes from. Secret scanning belongs
here and nowhere else, because the log is append-only: redaction must happen **before** the write.
There is no unwriting. Users will paste connection strings into free-text answers — this is the
one place to catch it.

## What to build

### Append

`ppa/ledger/store.py` — `append_event(event) -> str`:
- exclusive file lock on `events.ndjson` for the whole read-counter/write-line sequence
- monotonic `event_id` allocated under the same lock
- one JSON object per line, newline-terminated, UTF-8
- fsync before releasing the lock

### Secret scanning — `ppa/ledger/secrets.py`

`scan_and_redact(text) -> tuple[str, list[Finding]]`, called on **every free-text field** before
the event is constructed. Patterns to cover:

- API key shapes (`sk-`, `ghp_`, `AKIA`, long base64/hex runs ≥32 chars with high entropy)
- credentialed URIs — `postgres://user:pass@`, `mysql://`, `mongodb://`, `redis://`
- private key headers — `-----BEGIN ... PRIVATE KEY-----`
- `Authorization:` / `Bearer ` headers
- `.env`-style `PASSWORD=`, `SECRET=`, `TOKEN=` assignments

A hit is replaced with `[REDACTED:credential]` **before** the event is written. The raw value is
never constructed into an `Event` object, never logged, never held beyond the function.

The caller surfaces it to the user inline:

> I've redacted what looks like a credential from that answer. If it matters to the requirement,
> describe it rather than pasting it.

False positives are recoverable — the user rephrases. A written secret is not.

## Files touched

```
ppa/ledger/store.py
ppa/ledger/secrets.py
tests/test_ledger/test_append.py
tests/test_secrets/test_scan.py
```

## Done when

- [x] 1000 concurrent appends produce exactly 1000 well-formed lines, no interleaving, no lost IDs
- [x] Event IDs are strictly monotonic under concurrency
- [x] A fixture answer containing `postgres://u:p@host/db` is stored redacted
- [x] The raw credential appears nowhere in `events.ndjson`
- [x] Each of the five pattern families has a positive test and a near-miss negative test
- [x] The single-writer assumption is written into `README.md`

## Traps

Redaction after the append is worthless — the log is append-only and git may already have the
line. Scan on the way in, always.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/ tests/test_secrets/`
3. Commit: `git add -A && git commit -m "T06: Event log with inbound secret scanning"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t06_*.md completed_tasks\
   bash:     mv tasks/t06_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T06` on the board.

---

## Build record (completed 2026-09-24)

### The "exclusive file lock" is `threading.Lock`, not an OS-level lock — by design

The task's snippet describes "exclusive file lock on `events.ndjson`," but this project runs one
CLI process per project, and the task's own last Done-when box requires documenting a
"single-writer assumption" in `README.md` — which only makes sense if the lock's real scope is
narrower than cross-process. Implemented as an in-process `threading.Lock`, keyed by resolved file
path: it fully serializes the read-counter/allocate-id/write-line/fsync sequence for concurrent
threads in one process (proven by the 1000-concurrent-append test), but two separate OS processes
writing the same file could still interleave. Documented plainly in `README.md`'s new
"Single-writer assumption" section, and logged in `blockers.md` as a decision rather than left
implicit — this is exactly the kind of assumption a later task could violate by accident (e.g. a
second `ppa` process launched against the same project) without ever seeing an error.

### A real bug caught by the test suite before commit

The first `_AUTH_HEADER` regex matched only `Authorization: Bearer` (the header name plus the
literal word "Bearer") and stopped there, leaving the actual token — `abcdef1234567890` in the
test fixture — untouched and readable in the "redacted" output. Caught immediately by
`test_authorization_header_is_redacted` failing before anything was committed. Fixed by extending
the pattern to consume the whole `Authorization:\s*(?:Bearer\s+)?\S+` value in one match. Logged in
`blockers.md` as a resolved bug, same as bug #1/#2 — a same-session catch is still worth a row.

### Event ID allocation

`_next_event_id` keeps an in-memory counter per file path, seeded once per process by reading the
last line of the existing file (if any) and parsing its `event_id`. After that, every append from
the same process is O(1) rather than re-scanning the file. A fresh process (or a cleared cache,
tested explicitly) recovers correctly from whatever is already on disk — no separate counter file
needed, since the log itself is the durable record.

### What exists now

```
ppa/ledger/store.py                  # append_event(), event-id allocation, the lock
ppa/ledger/secrets.py                # scan_and_redact(), Finding, the five pattern families
tests/test_ledger/test_append.py     # 10 tests, including 1000-concurrent-append
tests/test_secrets/test_scan.py      # 19 tests, one positive + one near-miss per family
README.md                            # "Single-writer assumption" section added
```

### Verification

```
$ .venv/Scripts/python.exe -m pytest tests/test_ledger/test_append.py tests/test_secrets/test_scan.py -> 29 passed
$ .venv/Scripts/python.exe -m pytest                                                                    -> 227 passed
```

### Notes for whoever picks up T07

- `append_event(fields, path)` takes every `Event` field except `event_id` — the id is allocated
  inside the same lock as the write, so it can't be supplied up front. `path` is required, not
  defaulted, since `events.ndjson` is project-scoped and T06 doesn't own the project-root layout
  (T08 does).
- Entity ID allocation (`REQ-001`, `ASM-001`, …) is a **different** counter from the event's
  `EVT-nnnnnn` id — T07 owns that, in `project.json`, under the same lock pattern established here.
- `scan_and_redact` only runs over `source` and `reason` in `append_event` — `before`/`after` carry
  structured entity snapshots, not free text a user typed.
