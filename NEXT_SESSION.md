# Next session — pick up here

**Branch:** `blockers-add-fixed-by-column`, tracking `origin/blockers-add-fixed-by-column`. Still
the one live line of development. Phase F (Resilience and validation) is nearly done — T34 just
landed, leaving **T35 as the final task on the whole 35-task board.**

**Baseline:** full default suite (excludes `live_model`) — clean, exit 0, re-confirmed at the end of
this session after every production-code change T34 made. `pytest -m live_model` — every case run
individually this session passed (see below); the one combined `--live --matrix` invocation hit the
Claude Code subscription's own rolling usage limit mid-run once (not a code defect — see Decision #4
below), cleared on its own, and a full re-run afterward passed 18/18. Re-run the full suite once at
the start of a new session before trusting any of this.

**Current task:** T34 is done and committed (`2fc8578`, hash follow-up in `7345b7d`). Next up: **T35
— `tasks/t35_hardening_and_documentation.md`** (Phase F · Resilience and validation, the last task
on the board). Not yet opened or started this session. Read that file first; it has its own
Done-when checklist. One of its own boxes ("all three open decisions from §6.7 are resolved and
recorded") is **already true** as of T34 — `tasks/readme.md`'s own "Open decisions" table shows all
three resolved (#1, #2, #3), so T35 doesn't need to do anything there beyond confirming it, not
resolving anything new.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers), §2 (Decisions) and §3 (Bugs) are all
empty — the last three pending decisions (#4, #33, #34) were resolved this session and moved to §4.

**What T34 actually built** (read `completed_tasks/t34_eval_suite_and_baseline.md`'s own Build
record for full reasoning — this is just the map):

- **A real bug fixed before anything else could be trusted.** Five real model call sites
  (`ppa/agents/turn.py`, `ppa/agents/modes/{change,review}.py`, `ppa/agents/subagents/
  {guidance,research}.py`) all constructed a bare `ModelProvider()` instead of `ModelProvider.
  from_config(...)`, silently discarding `config/model.yaml`/`PPA_MODEL_TIER` on every real turn
  since T21. Fixed — `ppa/providers/model.py` gained `DEFAULT_CONFIG_PATH`, all five now call
  `ModelProvider.from_config(DEFAULT_CONFIG_PATH)`.
- **§2.17 invariant** — `tests/eval/test_llm_surface_invariant.py`, a static seam scan (greps for
  `.client(` call sites, asserts the set is exactly those same five, each declaring its own
  `LLM_SURFACE`). No live call needed for this test itself.
- **Eighteen S12.2 cases** — `tests/eval/cases/case_01..18_*.py`. Fourteen deterministic (no model
  call — proven directly against `ppa.tools.dispatch`, `ppa.recovery.retry`,
  `ppa.orchestrator.escalation`, `ppa.tools.approval`, `ppa.validation.*`, `ppa.engines.{impact,
  coverage}`). Four live (`case_01`, `03`, `13`, `14`, marked `live_model`) — each needed real
  correction after its first live attempt; see the Build record for exactly what each run showed and
  why the fix was made (case 3 in particular found that "non-critical" and "silently assumable" are
  different things — worth reading before touching `mode_clarify.md` again).
- **`ppa/agents/prompts/mode_clarify.md`** gained real, previously-missing guidance for
  `answer_kind="decide_later"` — nothing told a turn how to react to one before this session.
- **`tests/eval/rubric.py` + `tests/eval/scorecard.py`** — the metrics model and the "one command"
  (`python -m tests.eval.scorecard [--live] [--matrix ...] [--save PATH] [--compare PATH]`).
- **`tests/eval/test_decisions_33_34_clarify_session_level.py`** — one real 6-round `always_idk`
  session (against `f06_detailed_k8s_audit_alerting`) that closed blockers.md decisions #33 and #34
  in a single run, on the first live attempt: research routed at least once, the round-4 assumptions
  offer fired, the fatigue switch held from early on, and the anti-loop guard's forced escalation
  actually fired (a blocking `Unknown(route="GUIDANCE")`, no question ever repeated verbatim).
- **Decision #4 (model tier)** — `scripts/probe_model_tier.py` + `docs/decisions/model_tier.md`.
  Resolved: **`primary`** (Sonnet 5). `cheap` (Haiku 4.5) failed the established INTAKE quality bar
  and wasn't even faster; `deep` (Opus 5) passed but cost ~2.5x more for no measured benefit. Single
  representative probe (n=1 per tier) — re-probe before assuming this generalizes to a much larger
  run.
- **`tests/eval/baseline.json`** — recorded from all eighteen cases plus **one** matrix session
  (`f01_vague_internal_ops_tool` × `knows_their_stuff`), not the full sixty-combination grid, for the
  same wall-clock reasons T33's own handoff note already named (a single multi-round live session
  can run 10+ minutes; the full matrix would run for hours). The scorecard command's `--matrix` flag
  defaults to the full grid if no `--fixture`/`--persona` is named, so the *capability* exists even
  though this baseline didn't exercise all sixty.

**A note on live-model wall-clock and the subscription usage limit, for whoever picks this up
next:** a single multi-round session (5-6 rounds) takes on the order of 10-15 minutes; running
several live cases plus a session back-to-back in one sitting can hit the Claude Code subscription's
own rolling usage limit (this session hit it once, message: "You've hit your individual spend
limit... your session limit resets \<time\>"). It is not a code or prompt defect — waiting past the
stated reset time and retrying is enough (confirmed this session: an individual case that failed
with the limit message passed cleanly moments after the reset). Budget for this the same way you'd
budget for wall-clock: don't chain many live invocations in one sitting without slack, and if a live
case fails with that literal message in its own output, that is the tell — re-run it, don't debug it
as a regression.

**How to resume:**
1. Confirm you're on `blockers-add-fixed-by-column` (`git status`) and it's up to date with
   `origin/blockers-add-fixed-by-column`.
2. Set up (or activate) `.venv/` if this is a fresh worktree — `.venv/` is gitignored, so a new
   worktree needs `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
   before anything will run (from inside `product_planning_agent/`).
3. Run the full suite to reconfirm the baseline before touching anything.
4. Open `tasks/t35_hardening_and_documentation.md` and start there — the last task on the board.
5. Delete this file (or update it) once T35 is committed — it's a handoff note for the next
   session, not a permanent record like `blockers.md`.
