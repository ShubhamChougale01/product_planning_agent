# Next session — pick up here

**Branch:** `blockers-add-fixed-by-column`, tracking `origin/blockers-add-fixed-by-column`.

**The 35-task board is complete.** T35 (`completed_tasks/t35_hardening_and_documentation.md`) was
the last task and landed this session. `tasks/readme.md`'s board shows all 35 boxes ticked;
`tasks/` itself now holds only `readme.md` — every task file has moved to `completed_tasks/`.

**Baseline:** full default suite (excludes `live_model`) — 909 tests, 0 failures, 0 errors, 1
skipped, exit 0, re-confirmed at the end of this session after every production-code change T35
made (up from 902 at session start — 7 new tests, all for T35's own cost-instrumentation and
resume-after-crash work). `pytest -m live_model` was **not** re-run this session — T35 needed no
model calls (`Needs a model? No`, per its own task table), so nothing touched the live-model path.
Re-run it once before trusting it, the same caution T34's own handoff note gave.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers), §2 (Decisions) and §3 (Bugs) are all
empty, and nothing from this session needed a new row — T35 was pure implementation plus tests
plus docs, no genuine ambiguity or defect surfaced.

**What T35 actually built** (read `completed_tasks/t35_hardening_and_documentation.md`'s own Build
record for full reasoning — this is just the map):

- **Three of the four build items were already done** — crash recovery (T07's own materializer
  already excludes any uncommitted `txn_id`, proven directly by T32), session resumption
  (`open_project`/`read_digest` already rebuild everything fresh from disk, no caching, no
  wall-clock dependency), and `ppa why <id>` (built across T28/T31). This session's real job for
  those three was proving it end to end from the CLI's own entry points, in a new
  `tests/test_recovery/test_resume.py` — one test for a killed-mid-transaction session resuming
  with no manual repair, one for a week-old project's digest correctly re-anchoring "due soon" math
  to the real current moment rather than the ledger's own stale timestamps.
- **Cost instrumentation was the one genuinely new feature.** A new `EventType.TURN_COST_RECORDED`
  (`ppa/ledger/events.py`), written once per `run_turn` call by a new `_write_turn_cost_event`
  helper (`ppa/orchestrator/loop.py`) — `cost_usd` and `bundle.token_estimate` were both already
  computed per turn since T21/T34 but never persisted past the turn that produced them. Surfaced as
  `ppa status --cost` (a flag on the existing `status` command, not an eighth command — keeps the
  README's "seven commands" count accurate), folding a per-agent/per-mode breakdown via new
  `render_cost_report`/`_cost_rows` in `ppa/render/status_board.py`.
- **README rewritten**: an accurate Status section (all 35 tasks, not "T01 complete"), the seven
  real commands in a table, and a worked example built from *real captured CLI output* (a
  throwaway, uncommitted script seeded a demo project and ran the actual `typer.testing.CliRunner`
  against it) — not invented transcript text. The single-writer constraint and ledger-contents
  notice were already in the README from earlier sessions; this session added a "Crash recovery and
  resumption" section alongside them.
- **`docs/decisions/house_style_templates.md`** (new) — the one §6.7 decision (#1, Coditas
  templates) that had no dedicated file yet; #2 (`model_tier.md`) and #3 (`auth.md`) already existed
  from T34/T01. `tasks/readme.md`'s open-decisions table now links all three.

**How to resume, if there's ever a T36 or a new phase:**
1. Confirm you're on `blockers-add-fixed-by-column` (`git status`) and it's up to date with
   `origin/blockers-add-fixed-by-column`.
2. Set up (or activate) `.venv/` if this is a fresh worktree — `.venv/` is gitignored, so a new
   worktree needs `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
   before anything will run (from inside `product_planning_agent/`).
3. Run the full suite to reconfirm the baseline before touching anything.
4. There is no open task file — if new work is scoped, it needs its own task file in `tasks/`
   first, following the same shape every completed one in `completed_tasks/` already has.
5. This file can be deleted once its contents stop being useful — it's a handoff note, not a
   permanent record like `blockers.md`.
