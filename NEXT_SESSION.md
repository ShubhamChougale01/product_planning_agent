# Next session — pick up here

**Branch:** `blockers-add-fixed-by-column`, tracking `origin/blockers-add-fixed-by-column`. Still
the one live line of development — it absorbed T07–T30, and now T31–T33. Phase E (Product surface)
is complete; Phase F (Resilience and validation) is one task in (T32 of 4).

**Baseline:** full suite — 884 passed, 1 skipped, default `pytest` run (confirmed by re-running the
whole suite fresh at the end of this session, dot-count verified since the summary line didn't
survive output capture that run — don't read anything into that beyond a capture quirk). Separately, `pytest -m live_model` — T31–T33 added their own live proofs on top of the existing 9:
T31's `chat` end-to-end proof used a fixture agent (no live call needed, matching its own "Needs a
model? No"); T33's `tests/eval/test_matrix.py` ran 8 real, multi-round sessions (6 personas +
1 targeted defers_to_client run + 1 ten-fixture breakage survey), all passing after one in-flight
correction (decision #41). Re-run the full suite once at the start of a new session before trusting
any of this — it was last confirmed clean at the end of this session, not verified again since.

**Current task:** T31 through T33 are done and committed. Next up: T34 —
`tasks/t34_eval_suite_and_baseline.md` (Phase F · Resilience and validation). Not yet opened or
started this session. Read that file first; it has its own Done-when checklist to work through.
**Decision #4** ("which model tier for eval runs") is explicitly T34's own to resolve — don't guess
at it before then.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers) and §3 (Bugs) are both empty.

**Decisions pending confirmation (not blockers — safe to keep building on):**
- **#33** (T25) — three Done-when boxes describing session-level/multi-round CLARIFY behavior
  (research routed at least once per session, round-4 assumptions offer, three-consecutive-
  `dont_know` triggering assumption-heavy mode) — **still resolves at T34**. T33 built the harness
  that makes this checkable (`tests/eval/harness.py::run_session`, real multi-round sessions) but
  its own tests never targeted these three specific conditions — don't assume they're proven just
  because multi-round sessions now run cleanly.
- **#34** (T26) — the `always_idk` persona's own live multi-round proof — **still resolves at T34**
  for the same reason: T33's `always_idk` run completed 4 real rounds without crashing, which is
  *not* the same claim as "the anti-loop guard's forced escalation actually fired." Check for a real
  escalation/routing event, don't just check for survival.
- **#4** — which model tier for eval runs — **resolves at T34**. Also worth noting: `PPA_MODEL_
  TIER` is not actually wired into real Discovery turns yet (`ppa.agents.turn._run_one_sdk_turn`
  calls `ModelProvider()` with no config, never `.from_config()`) — every live call this build has
  ever made, including all of T33's, ran on the default tier (`primary` / Sonnet-5). If T34 wants
  a cheaper tier for a large eval run, that wiring has to be added first.

**What T31–T33 actually built** (read each task's own Build record in `completed_tasks/` for full
reasoning — this is just the map):
- **T31** — `ppa/render/status_board.py` (the whole status board, drawn purely from already-proven
  engines — coverage, readiness, open_items, dates — plus a plain fold over `events.ndjson` for
  session/round/`DiscoveryMode`). Real CLI commands: `chat` (the main loop), `status --items`,
  `history`, `force-ready`, `why` (now with provenance from `audit.ndjson`). **Decision #39**: six
  judgment calls, including adding `ppa.tools.interaction.answer_pending_question` (the "caller
  answers a PENDING question later" half `ask_user`'s own docstring always named as T31's job).
- **T32** — `ppa/recovery/{transaction,retry}.py` + `ppa/orchestrator/escalation.py`. Transaction
  rollback was already true by construction (T07/T21); this task added the independent checkpoint/
  verify proof rather than a second mechanism. `retry.py` gives bounded, budget-of-3, TRANSIENT-only
  retry with the task's own `PARTIAL_FAILURE` JSON shape. `escalation.py` structurally enforces
  "every escalation ends in a concrete question" via required Pydantic fields. **Decision #40**:
  "local recovery first" is proven generically (a stand-in function), not by rewiring T29's real
  research subagent — out of this task's own file scope.
- **T33** — `tests/eval/fixtures/*.yaml` (ten fixtures across five axes, two flagged adversarial),
  `tests/eval/personas.py` (six deterministic personas), `tests/eval/harness.py` (`run_session`,
  drives one real multi-round Discovery session per fixture/persona pair — launchable as
  `python -m tests.eval.harness`). **Decision #41**: a real finding, corrected in-flight —
  `defers_to_client`'s first live run used an internal-only fixture and produced nothing external;
  correct agent behavior given no client existed in that project's context, not a bug. Fixed by
  switching to a fixture that actually establishes a client.

**A note on live flakiness, for whoever picks this up next:** the exact same non-determinism kept
recurring on `pytest -m live_model`'s *combined* run through T27/T28/T30 (never on an isolated
re-run of just the failing test) — see `blockers.md`'s own decisions/bugs for specifics. Treat a
lone failure in a *combined* `live_model` run as suspect-flaky first — re-run that one test alone
before concluding a real regression. T33's own multi-round sessions are individually much longer
(a single 5-round session took ~13.5 minutes; the full 8-test matrix took ~1h31m) — budget real
wall-clock time before running `tests/eval/test_matrix.py` again, and prefer running one test at a
time (`pytest -m live_model tests/eval/test_matrix.py::test_name`) over the whole file when only
one result is in question.

**How to resume:**
1. Confirm you're on `blockers-add-fixed-by-column` (`git status`) and it's up to date with
   `origin/blockers-add-fixed-by-column`.
2. Set up (or activate) `.venv/` if this is a fresh worktree — `.venv/` is gitignored, so a new
   worktree needs `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
   before anything will run (from inside `product_planning_agent/`).
3. Run the full suite to reconfirm the baseline before touching anything.
4. Open `tasks/t34_eval_suite_and_baseline.md` and start there.
5. Delete this file (or update it) once T34 is committed — it's a handoff note for the next
   session, not a permanent record like `blockers.md`.
