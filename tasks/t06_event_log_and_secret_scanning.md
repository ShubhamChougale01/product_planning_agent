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

- [ ] 1000 concurrent appends produce exactly 1000 well-formed lines, no interleaving, no lost IDs
- [ ] Event IDs are strictly monotonic under concurrency
- [ ] A fixture answer containing `postgres://u:p@host/db` is stored redacted
- [ ] The raw credential appears nowhere in `events.ndjson`
- [ ] Each of the five pattern families has a positive test and a near-miss negative test
- [ ] The single-writer assumption is written into `README.md`

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
