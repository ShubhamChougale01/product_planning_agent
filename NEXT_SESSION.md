# Next session — pick up here

**Branch:** `blockers-add-fixed-by-column`, tracking `origin/blockers-add-fixed-by-column`. This
branch absorbed the `t07-t15-implementation` merge (PR #2), then added a "Fixed by (commit/PR)"
column to `blockers.md`'s tables, then continued straight on to T16–T20 — there is no longer a
separate T07–T15-only branch; this one is the live line of development.

**Baseline:** full suite — 648/648 passing, 1 skipped (intentional — a parametrize case in
`tests/test_agents/test_transitions.py` that doesn't apply to its own parameter).

**Current task:** T16 through T20 are done and committed. Next up: T21 —
`tasks/t21_preconditions_and_outer_loop.md`. Not yet opened or started this session. Read that
file first; it has its own Done-when checklist to work through. **Note: T21 is the first task that
needs a model** ("first agent invocation" per `tasks/readme.md`'s board) — confirm auth/model
config is actually working (`ppa doctor` or equivalent) before assuming a dry run will succeed.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers) and §3 (Bugs) are both empty.

**Decisions taken but not yet written to disk:** none. Everything decided through T20 is already
committed on this branch, including every "Fixed by" hash back-fill.

**Decisions pending confirmation (not blockers — safe to keep building on):**
- **#19** — `check_readiness`'s three not-yet-buildable inputs (`confirmed_areas`,
  `unresolved_conflicts`, `review_approved`) are accepted as caller-supplied parameters, since
  nothing before T30 (Review mode) actually produces them. Stays pending until the build reaches
  T30.

**Resolved since this note was last written (see `blockers.md` §4 for full detail on each):**
- **#24** — T16's `manage_decision(defer)` Done-when box reworded: `expected_decision_date` is
  always tool-computed (T12's rule), never caller-supplied. Audit is self-recorded inside each
  `manage_*`/`ask_user`/`manage_linear_issue` writer, not left to `ppa/tools/dispatch.py` (which
  T19 deliberately left untouched — see #26).
- **#25** — T18's approval events (`approval.granted`/`approval.revoked`) are *folded*
  (`ppa.tools.approval.current_approval`), not *materialized* under `entities/` — they carry no
  `entity_id` and aren't one of T02's seven locked entity types.
- **#26** — T19 does not wire `ppa/tools/hooks.py::pre_tool_use` into `ppa/tools/dispatch.py` —
  not in T19's own file scope, and would break two of T14's existing `test_grants.py` tests (fake
  handlers that don't return real `ToolResult` JSON). Whichever task next touches `dispatch.py`'s
  own "T19 inserts layers 2-5 here" marker should fix those two fakes at the same time.
- **#27** — T20's `Agent.id` values are the real, already-shipped `GRANTS` keys (`"discovery"`,
  not `"DiscoveryAgent"`) — the task file's own pseudocode was stale.

**What T16–T20 actually built** (read each task's own Build record in `completed_tasks/` for full
reasoning — this is just the map):
- **T16** — `ppa/tools/discovery_tools.py` gained the four `manage_*` writers
  (`manage_requirement`/`manage_assumption`/`manage_decision`/`manage_unknown`), all routed through
  one `_generic_transition` for every non-create operation. Mandatory provenance on
  `manage_requirement(create)`; the one semantic rule this build needs (a Requirement can't
  `CONFIRM` while a blocking `Unknown` covering the same area is `OPEN`) registered into
  `ppa.validation.semantic`.
- **T17** — `ppa/tools/interaction.py` (`ask_user`, ≤5 questions/batch) and a minimal
  `ppa/render/question_card.py`. Answered questions produce three events (`QUESTION_ASKED` ->
  `QUESTION_REPLACED` -> `ANSWER_RECORDED`), matching `QuestionAnswer`'s own two-id-series docstring
  literally.
- **T18** — `ppa/tools/planning_tools.py`/`delivery_tools.py` (seven pure `NOT_IMPLEMENTED` stubs)
  plus `ppa/tools/approval.py` (the real approval gate — `scope_hash`, grant/revoke events,
  `@requires_approval` decorator) guarding `manage_linear_issue`, the one Delivery tool with real
  guardrails today.
- **T19** — Filled all five `ppa/validation/*.py` stubs for real; `ppa/tools/hooks.py::pre_tool_use`
  runs layers 1-3 (permission/schema/workflow) in order. `validation_layer_failed` is inferred once
  (`ppa/validation/__init__.py::infer_validation_layer`) and threaded through every writer's
  self-recorded audit call, including a real gap found and fixed in the approval gate's own
  rejection path (it wasn't auditing at all before this).
- **T20** — `ppa/agents/base.py` (`Agent` protocol, `AgentResult`/`AgentResultStatus`,
  `RecoveryDecision`), six real agent registrations in `ppa/agents/registry.py::AGENTS`, and
  `ppa/workflow/{transitions.yaml,machine.py}` — the global state machine as data. Found and fixed
  two real circular-import bugs between `ppa.agents.base`/`ppa.agents.registry`/`ppa.tools.dispatch`
  while wiring the six agents in (`BaseAgent.grant()` now imports `grant_for` inside the method
  body, not at module level).

**How to resume:**
1. Confirm you're on `blockers-add-fixed-by-column` (`git status`) and it's up to date with
   `origin/blockers-add-fixed-by-column`.
2. Set up (or activate) `.venv/` if this is a fresh worktree — `.venv/` is gitignored, so a new
   worktree needs `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
   before anything will run.
3. Run the full suite to reconfirm the 648-passing baseline before touching anything.
4. Open `tasks/t21_preconditions_and_outer_loop.md` and start there. This is the first task that
   actually invokes a model — read it fully before assuming the zero-cost pattern of T13-T20 still
   applies.
5. Delete this file (or update it) once T21 is committed — it's a handoff note for the next
   session, not a permanent record like `blockers.md`.
