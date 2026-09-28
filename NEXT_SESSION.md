# Next session — pick up here

**Branch:** `blockers-add-fixed-by-column`, tracking `origin/blockers-add-fixed-by-column`. Still
the one live line of development — it absorbed T07–T15, the blockers.md "Fixed by" column, T16–T20,
and now T21–T25.

**Baseline:** full suite — 770/770 passing, 1 skipped, default `pytest` run. Separately,
`pytest -m live_model` — 3 passing (T23's real-turn proof, T24's intake eval, T25's clarify eval).
Both were reconfirmed clean at the end of this session.

**Current task:** T21 through T25 are done and committed. Next up: T26 —
`tasks/t26_dont_know_routing.md`. Not yet opened or started this session. Read that file first; it
has its own Done-when checklist to work through.

**Unresolved blockers:** none. `blockers.md` §1 (Blockers) and §3 (Bugs) are both empty — every bug
found this session (#6–#12, seven of them, all found live while building T24) is resolved and moved
to §4.

**Decisions pending confirmation (not blockers — safe to keep building on):**
- **#19** — `check_readiness`'s three not-yet-buildable inputs, unchanged since T10; still resolves
  at T30.
- **#33** (new this session) — three of T25's own Done-when boxes describe session-level or
  multi-round CLARIFY behavior (research routing "at least one per session," the round-4
  assumptions offer, the three-`dont_know` fatigue switch) that a single live round can't exercise
  end to end. All three are built and unit-tested at the deterministic-engine layer
  (`ppa.engines.question_engine`) and instructed in `mode_clarify.md`'s own prompt — **resolves at
  T33/T34**, which are exactly the tasks built to run scripted, multi-round sessions against
  personas. Nothing here blocks continuing to T26.

**What T21–T25 actually built** (read each task's own Build record in `completed_tasks/` for full
reasoning — this is just the map):
- **T21** — `ppa/orchestrator/{loop,preconditions,dispatch,context}.py`. The outer loop (DESIGN.md
  §2.11), driven by workflow state and the readiness gate, never by model output. All seven
  `AgentResultStatus` outcomes handled explicitly. Proven almost entirely without a model in the
  loop; the one real SDK-turn proof lives in `scripts/verify_first_turn.py` (decision #28 — the
  zero-cost-suite principle this whole session leaned on repeatedly).
- **T22** — `tests/test_permissions/test_guardrails.py` + `tests/test_agents/test_prohibitions.py`.
  Every DESIGN.md §2.13/§2.19/§2.4 guardrail traced to a passing test, reusing already-shipped
  mechanisms rather than duplicating them.
- **T23** — Discovery's first real system prompt and turn behavior
  (`ppa/agents/{discovery,turn}.py`, `ppa/agents/prompts/*.md`, `ppa/config/autonomy.py`). Mode-
  scoped tool subsets enforced at the harness level. **Found bug #5**: `allowed_tool_names` needs
  the fully-qualified `mcp__<server>__<tool>` form, not a bare name.
- **T24** — Intake mode (`ppa/agents/modes/intake.py`). This is the task where a real Discovery
  turn first tried to actually persist something, which surfaced **bugs #6–#12** — in order: the
  built-in Claude Code toolset was never disabled (`tools=[]` missing, the single most severe
  finding this session); in-process MCP tools come back deferred and need one literal `ToolSearch`
  call per tool to resolve reliably; `ppa/tools/registry.py` never imported the real tool modules,
  so the tool registry was empty in every real process; tool handlers had no way to know the live
  turn's real `project_slug`/`projects_root`; the MCP boundary's string-only schema needs explicit
  list/bool coercion before reaching a writer function; `manage_assumption(create)` silently
  defaulted `user_confirmation_required` to `False`; and Intake's own mode-advancement condition
  was backwards. With all seven fixed, a real turn against DESIGN.md's own "vendor invoice tracker"
  example produces a fully real, fully persisted round end to end.
- **T25** — Clarify mode and the question engine (`ppa/engines/question_engine.py`,
  `ppa/agents/modes/clarify.py`). The deterministic quarter of the five-step pipeline (find gaps,
  score, cap, fatigue, soft cap) as real code; the model still owns candidate generation and the
  qualitative filter, guided by `mode_clarify.md`. The filter didn't fire on the first live
  attempt (0 assumptions recorded) — strengthened the prompt to require walking the whole gap list
  explicitly; the next live run passed cleanly.

**A note on live-model testing, for whoever picks this up next:** this session added a
`live_model` pytest marker (decision #31) — any test that makes a real call through
`ModelProvider` must carry `@pytest.mark.live_model`, and `pyproject.toml`'s `addopts` excludes it
from the default `pytest` run. Run those explicitly with `pytest -m live_model`. T26 onward is
also "Needs a model: Yes" — expect to use this marker again, and expect to find more of this exact
shape of bug (something that only breaks when a *real* model, through the *real* SDK, tries to
actually call a tool) — `pytest`'s own green baseline does not cover that path, deliberately, to
keep the default suite free.

**How to resume:**
1. Confirm you're on `blockers-add-fixed-by-column` (`git status`) and it's up to date with
   `origin/blockers-add-fixed-by-column`.
2. Set up (or activate) `.venv/` if this is a fresh worktree — `.venv/` is gitignored, so a new
   worktree needs `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"`
   before anything will run (from inside `product_planning_agent/`).
3. Run the full suite to reconfirm the 770-passing baseline before touching anything. Optionally
   also run `pytest -m live_model` to reconfirm the 3 real-model tests still pass.
4. Open `tasks/t26_dont_know_routing.md` and start there.
5. Delete this file (or update it) once T26 is committed — it's a handoff note for the next
   session, not a permanent record like `blockers.md`.
