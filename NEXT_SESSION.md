# Next session — pick up here

**Branch:** `t07-t15-implementation`, branched off `origin/main` at `0079f71`
(merge of decision #11's fix). This branch is for T07–T15 code only — no
plan-document changes bundled in. `main` stays frozen at T06 + decision #11
until this branch is merged back.

**Baseline:** full suite — 246/246 passing (227 at branch start + 19 added
by T07).

**Current task:** T07 is done and committed. Next up: T08 —
`tasks/t08_project_lifecycle_audit_git.md`. Not yet opened or started this
session. Read that file first; it has its own Done-when checklist to work
through.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers) and §3 (Bugs) are
both empty.

**Decisions taken but not yet written to disk:** none. Everything decided
through T07 (including decision #14 below) is already committed on this
branch.

**Decisions pending confirmation (not blockers — safe to keep building on):**
- **#14** — entity file layout (`entities/<entity_id>.json`, flat) is an
  assumption filling a gap in DESIGN.md §2.6, flagged in `blockers.md` for
  developer confirmation. T08 is the next task that touches this area
  (project lifecycle / `.planning/` directory creation) — worth confirming
  before T08 bakes in more structure around it, but not a hard blocker.

**What T07 actually built** (read `completed_tasks/t07_materializer_ids_idempotency.md`'s
Build record for the full reasoning):
- `ppa/ledger/materialize.py` — `materialize(entity_id, path)`, `rebuild_all(path)`,
  `entity_type_for(entity_id)`. Folds `events.ndjson` down to the latest
  committed `after` snapshot per entity, ignoring any transaction that never
  reached `txn.commit`.
- `ppa/ledger/store.py` (extended) — `allocate_id(prefix, path)`,
  `append_event_with_id(fields, path, *, id_prefix=None, idem_key=None) -> WriteResult`.
  Both share `append_event`'s existing per-path lock; `append_event`'s own
  signature/return type is untouched.
- `project.json` (sibling of `events.ndjson`) now holds `id_counters` and
  `idempotency` — T08 owns the rest of its shape (project name, profile,
  workflow_state, ledger_version).

**How to resume:**
1. Confirm you're on `t07-t15-implementation` (`git status`).
2. Run the full suite to reconfirm the 246-passing baseline before touching
   anything.
3. Open `tasks/t08_project_lifecycle_audit_git.md` and start there.
4. Delete this file (or update it) once T08 is committed — it's a handoff
   note for the next session, not a permanent record like `blockers.md`.
