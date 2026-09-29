# Next session — pick up here

**Branch:** `blockers-add-fixed-by-column`, tracking `origin/blockers-add-fixed-by-column`. Still
the one live line of development — it absorbed T07–T15, the blockers.md "Fixed by" column, T16–T20,
T21–T25, and now T26–T30. Phase D (Discovery Agent — the intelligence layer) is fully complete.

**Baseline:** full suite — 829/829 passing, 1 skipped, default `pytest` run. Separately,
`pytest -m live_model` — 9 passing (T23's real-turn proof, T24's intake eval, T25's clarify eval,
T26's dont-know eval, T27's external-input eval, T28's guidance eval, T29's research eval, T30's
review eval, T30's change eval). All reconfirmed clean at the end of this session — one flaky
pre-existing test (`test_clarify.py`/`test_research.py`, model non-determinism, not code) recurred
across multiple runs this session; always passed clean on an isolated retry. See "A note on live
flakiness" below.

**Current task:** T26 through T30 are done and committed. Next up: T31 —
`tasks/t31_cli_and_status_board.md` (Phase E · Product surface). Not yet opened or started this
session. Read that file first; it has its own Done-when checklist to work through.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers) and §3 (Bugs) are both empty.

**Decisions pending confirmation (not blockers — safe to keep building on):**
- **#33** (T25) — three Done-when boxes describing session-level/multi-round CLARIFY behavior,
  proven at the engine layer only — **resolves at T33/T34**.
- **#34** (T26) — the `always_idk` persona's own multi-round proof, same shape as #33 — **resolves
  at T33/T34**.
- **#4** — which model tier for eval runs — **resolves at T34**.

Decision #19 (T10's three not-yet-buildable readiness-gate inputs) is now **resolved** — T30 wired
all three to real event-sourced state, exactly as T10's own row predicted.

**What T26–T30 actually built** (read each task's own Build record in `completed_tasks/` for full
reasoning — this is just the map):
- **T26** — `ppa/engines/dont_know_classifier.py` (the seven kinds, the routing table as code, the
  anti-loop guard's arithmetic) + `ppa/agents/modes/dont_know.py` (shape contract). No new MCP
  tool — every route reachable with `ask_user`/`manage_assumption`/`manage_decision`/
  `manage_unknown`. **Bug #13**: `manage_assumption`'s `ToolSpec` never exposed `provisional` to
  the model.
- **T27** — `ppa/agents/modes/external.py` + `ppa/render/client_questions.py` (`ppa client-
  questions`, a real CLI command). **Decision #35**: `needs_external_input` became a three-call
  sequence (`manage_unknown(record, owner_type=external)` + `manage_assumption(create,
  provisional=True)` + `manage_unknown(convert)`) so the questionnaire has question/why/blocking/
  area, not just a bare assumption.
- **T28** — `ppa/agents/subagents/guidance.py` (real `GuidanceBrief`, its own isolated SDK turn,
  own grant) + `ppa/render/guidance_card.py` (`ppa why <dec-id>`, a real CLI command). **Decision
  #36**: `manage_research` (create/link_decision/supersede) built from scratch — nothing before
  this task ever wrote a real `RES-nnn`.
- **T29** — `ppa/providers/research.py` (the three-state degradation seam) + `ppa/agents/
  subagents/research.py` (`run_research_session` batches the whole `RESEARCH_REQUIRED` queue in
  one turn). **Decision #37**: `available()` gates before any model call; the FAILED message is
  built directly, never through `provider.research()` (deliberately unimplemented on the real
  provider).
- **T30** — `ppa/agents/modes/review.py` (REVIEW's grant widened for `manage_assumption`;
  `grant_review_approval` is a plain function, never a tool, mirroring T18's own approval rule) +
  `ppa/agents/modes/change.py` (`run_change_session`: detect via T11's `find_conflict_candidates`,
  adjudicate via the new `manage_conflict` tool, supersede+create, `analyze_impact`, rewind
  `CHANGE_REQUESTED -> DISCOVERY`). **Decision #38**: five related judgment calls, including
  "change handling is not a `DiscoveryMode`" (it's the *global* workflow state, a different level)
  — it runs against `agent_id="discovery"`'s full grant directly, same shape T28/T29's subagents
  use for a different reason.

**A note on live flakiness, for whoever picks this up next:** the exact same non-determinism keeps
recurring on `pytest -m live_model`'s *combined* run (never on an isolated re-run of just the
failing test) — `test_clarify.py::test_clarify_round_on_a_post_intake_ledger_meets_the_per_round_
shape` (T25) failed on the T27, T28 and T30 sessions' first combined runs; `test_research.py::
test_a_real_research_session_batches_the_queue_and_persists_findings` (T29) failed once on T30's
combined run. Every single time, an isolated re-run of just that one test passed clean. Treat a
lone failure in the *combined* `live_model` run as suspect-flaky first — re-run that one test alone
before concluding a real regression; only escalate if the isolated retry also fails.

**How to resume:**
1. Confirm you're on `blockers-add-fixed-by-column` (`git status`) and it's up to date with
   `origin/blockers-add-fixed-by-column`.
2. Set up (or activate) `.venv/` if this is a fresh worktree — `.venv/` is gitignored, so a new
   worktree needs `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
   before anything will run (from inside `product_planning_agent/`).
3. Run the full suite to reconfirm the 829-passing baseline before touching anything. Optionally
   also run `pytest -m live_model` to reconfirm the 9 real-model tests still pass (watch for the
   flakiness note above — a lone failure there is not automatically a regression).
4. Open `tasks/t31_cli_and_status_board.md` and start there. It has no listed model requirement
   ("Needs a model? No") — the first task since T20 that doesn't.
5. Delete this file (or update it) once T31 is committed — it's a handoff note for the next
   session, not a permanent record like `blockers.md`.
