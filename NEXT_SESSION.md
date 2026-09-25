# Next session — pick up here

**Branch:** `t07-t15-implementation`, branched off `origin/main` at `0079f71`
(merge of decision #11's fix). This branch is for T07–T15 code only — no
plan-document changes bundled in. `main` stays frozen at T06 + decision #11
until this branch is merged back.

**Baseline:** full suite — 518/518 passing (227 at branch start + 291 added
across T07–T15).

**Current task:** T08 through T15 are done and committed. Next up: T16 —
`tasks/t16_manage_writer_tools.md`. Not yet opened or started this session.
Read that file first; it has its own Done-when checklist to work through.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers) and §3 (Bugs) are
both empty.

**Decisions taken but not yet written to disk:** none. Everything decided
through T15 is already committed on this branch.

**Decisions pending confirmation (not blockers — safe to keep building on):**
- **#14** — entity file layout (`entities/<entity_id>.json`, flat). Flagged
  since T07; still nothing downstream depends on the exact path.
- **#19** — `check_readiness`'s three not-yet-buildable inputs
  (`confirmed_areas`, `unresolved_conflicts`, `review_approved`) are
  accepted as caller-supplied parameters, since nothing before T30 (Review
  mode) actually produces them. T30 is the task that needs to decide how
  each gets persisted (likely new event types).
- **#21** — `expected_decision_date` takes `affects` as an explicit
  argument rather than deriving it from a `Decision` object, since
  `Decision` carries no field to classify "affects architecture vs scope."
  Revisit if a future task adds that field to `Decision`.

**What T08–T15 actually built** (read each task's own Build record in
`completed_tasks/` for full reasoning — this is just the map):
- **T08** — `ppa/ledger/project.py` (`create_project`/`open_project`/
  `list_projects`), `ppa/ledger/gitops.py` (git init/commit/commit_turn,
  no remote ever configured), `ppa/ledger/audit.py` (`audit.ndjson`,
  hash-only inputs_ref).
- **T09** — `ppa/ledger/digest.py` (`generate_digest`/`read_digest`).
  Coverage state is rendered, not computed — T10 owns that exclusively.
  Also added `ppa/ledger/materialize.py::current_entities` (no-file-write
  fold, for reads that shouldn't pay `rebuild_all`'s disk cost).
- **T10** — `ppa/engines/coverage.py` (`compute_coverage`/`progress`, no
  public setter) and `ppa/engines/readiness.py` (`check_readiness`/
  `force_ready`, seven gate conditions, `Blocker`).
- **T11** — `ppa/engines/impact.py` (`analyze_impact`, BFS + cycle
  detection) and `ppa/engines/conflicts.py` (`find_conflict_candidates`,
  five cheap signals, scoped to `CONFIRMED` Requirements/Assumptions only).
- **T12** — `ppa/engines/dates.py` (`expected_decision_date`/`is_overdue`/
  `due_within`, frozen-clock discipline) and `ppa/engines/open_items.py`
  (`collect_open_items`). Refactored T09's digest to use both instead of
  its own hand-rolled date filter.
- **T13** — `ppa/tools/spec.py` (`ToolSpec`, `render_description`),
  `ppa/tools/registry.py` (`register`/`get`/`tools_for_agent`, validated at
  registration time), `ppa/tools/server.py` (`server_for`/
  `granted_sdk_tools`, wired to the real `claude-agent-sdk`).
- **T14** — `ppa/agents/registry.py` (static `GRANTS` table, `grant_for` —
  this file's stub comment wrongly said T20; corrected) and
  `ppa/tools/dispatch.py` (`dispatch`, permission-first, audits every
  rejection).
- **T15** — `ppa/tools/discovery_tools.py` now has real
  `read_planning_state` (all seven scopes, each a thin wrapper over a
  Phase-A engine), registered and granted to every reading agent. Also
  fixed a real bug (logged as bug #4): T13/T14's `clear_registry()` test
  fixtures could permanently erase real tool registrations made by an
  already-imported production module — added `registry.py::snapshot()`/
  `restore()` and switched every fixture to use them.

**How to resume:**
1. Confirm you're on `t07-t15-implementation` (`git status`).
2. Run the full suite to reconfirm the 518-passing baseline before touching
   anything.
3. Open `tasks/t16_manage_writer_tools.md` and start there.
4. Delete this file (or update it) once T16 is committed — it's a handoff
   note for the next session, not a permanent record like `blockers.md`.
