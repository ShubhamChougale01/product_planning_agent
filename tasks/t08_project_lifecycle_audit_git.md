# T08 — Project lifecycle, audit log, git

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.16, §2.19.1, S2.5–S2.7 |

## Prerequisites

- [ ] **T07**

## Why this task exists

Projects are the unit of work and each is its own git repo. Two deliberate choices here: the
audit log is separate from the event log, and new projects have **no git remote**. The ledger
holds client requirements and answers verbatim; it should not leave the machine by accident.

## What to build

### Project lifecycle

`create_project(name, seed_requirement, profile) -> Project`:
- create `projects/<slug>/.planning/`
- `git init` — and **configure no remote**
- write a `.gitignore` template excluding `*.local.*` and `scratch/`
- emit `project.created`
- print the notice: *the ledger stores your requirements and answers verbatim, including client
  information; it is a local git repo; add a remote only if that is appropriate for this project*

`open_project(slug)`, `list_projects()`.

### Audit log — `ppa/ledger/audit.py`

Separate file, `audit.ndjson`. Records **every tool invocation**, including reads, rejections and
retries — things that never become events.

```
agent · tool · operation · ts · workflow_state · inputs_ref · reason ·
result(success|category|code) · validation_layer_failed · retry_attempt ·
ledger_version_before · ledger_version_after · txn_id
```

`inputs_ref` is a **content hash plus entity pointer, never the raw payload** — so a value that
slipped past T06's scanner does not get a second home here.

Two logs, deliberately: `events.ndjson` stays semantic and replayable; `audit.ndjson` is
observability and is never replayed.

### Git auto-commit

`commit_turn(events)` — message generated from the turn's events, e.g.
`"round 3: +2 requirements, +1 assumption, resolved UNK-004"`.

## Files touched

```
ppa/ledger/project.py
ppa/ledger/audit.py
ppa/ledger/gitops.py
tests/test_ledger/test_project.py
```

## Done when

- [ ] Two projects coexist with fully independent ledgers
- [ ] A freshly created project has **zero** git remotes — assert it
- [ ] A rejected tool call appears in `audit.ndjson` and leaves `events.ndjson` untouched
- [ ] No tool input *value* is recoverable from the audit log — only hashes and pointers
- [ ] `git log --oneline` reads as a comprehensible planning narrative
- [ ] The verbatim-storage notice is shown on `ppa new`

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_ledger/`
3. Commit: `git add -A && git commit -m "T08: Project lifecycle, audit log, git"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t08_*.md completed_tasks\
   bash:     mv tasks/t08_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T08` on the board.
