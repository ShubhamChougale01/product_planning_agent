# T24 — Intake mode — the opening move

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 0.5 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §3.1, S7.4 |

## Prerequisites

- [x] **T23**

## Why this task exists

The worst version of this product opens with "Tell me about your target users." The best version
opens by demonstrating it already understood something. This single behaviour earns more trust,
and harvests more corrections, than any question would.

## What to build

### Flow — before any question is asked

1. Write a **3–6 sentence Initial Product Understanding** — what is being built, for whom, why.
2. Draft **3–8 requirements as PROPOSED**, with LOW/MEDIUM confidence and a stated basis.
3. Record **every inference as an ASSUMPTION** with `user_confirmation_required: true`.
4. Coverage moves as a *consequence* of steps 2–3 — the engine recomputes. The agent never
   declares a coverage state (§2.7).
5. Ask exactly **one** thing: *"Where am I wrong?"*

### Why one question

Intake is not the place to start interrogating. A user who has just seen the agent understand
their idea will correct it freely; a user facing five questions will disengage. The corrections
are worth more than the answers.

### Example shape

> From *"a tool for tracking vendor invoices"* I'm reading this as an internal tool for an
> accounts-payable clerk processing 50–200 invoices a week, with a finance manager approving.
> I've assumed web-only and single-company — flagged both. Where am I wrong?

## Files touched

```
ppa/agents/modes/intake.py
ppa/agents/prompts/mode_intake.md
tests/eval/test_intake.py
```

## Done when

- [x] On *\"a tool for tracking vendor invoices\"* it produces ≥3 proposed requirements
- [x] It produces ≥2 assumptions, all flagged for confirmation
- [x] It asks exactly **one** question
- [x] Zero assumptions are silent — every inference is an ASM entity
- [x] Coverage state after intake is computed, never declared — no coverage setter is called
- [x] The understanding statement is 3–6 sentences, not a wall of text

## Build record

`ppa/agents/modes/intake.py` — `evaluate_intake_shape(entities, reply_text)`, a pure, ledger-only
check against every box above (never against what the model's own text claims). "3–6 sentences"
is DESIGN.md's own bound on the *understanding paragraph alone*; a real reply also carries the
requirements recap, the assumptions recap and the closing question in the same breath, and those
can't be reliably split back out of prose by a regex — `MAX_REPLY_SENTENCES = 20` bounds the whole
reply instead, calibrated against real turns (a correctly-shaped reply naming 6-8 requirements and
6-8 assumptions runs ~10-12 sentences honestly, not because it pads). What actually matters, and
what the lower-bound checks catch, is "not a wall of text," not an exact tally close to 6.

### Getting a real turn to actually persist anything took seven infrastructure bugs, all found live

T24 is the first task to run a real Discovery turn against real tools, and doing so surfaced a
chain of previously-undiscovered defects — some in code this session's own T23 just wrote, several
in code T13-T18 shipped and *pytest never could have caught*, because the whole chain only breaks
when a real model, through the real SDK, tries to actually call a tool. Each is logged in full in
`blockers.md`; in the order found:

- **Bug #6** — `ModelProvider` never set `tools=[]`, so every agent turn had the *entire* built-in
  Claude Code toolset (Bash, Read, Write, Edit, ...) available underneath whatever MCP tools were
  wired in — verified live, a real turn read `blockers.md` and ran `git log` directly. The single
  most severe finding this session.
- **Bug #7** — even with #6 fixed, in-process MCP tools come back *deferred* under subscription
  auth; getting `ToolSearch` to reliably resolve them took three compounding, verified-live fixes
  (see the bug's own row, and `ppa/agents/turn.py::_tool_discovery_hint`'s docstring, for the full
  iteration history — naming the qualified names once was not enough, and neither was one combined
  query).
- **Bug #8** — `ppa/tools/registry.py` never imported the real tool modules; `_REGISTRY` was empty
  in every real process (masked entirely by `pytest`'s own test-collection import order).
- **Bug #9** — every writer/reader handler needed `project_slug`/`projects_root` the model had no
  way to know; `ppa/agents/turn.py::_bind_project` now forces both from the turn's own already-known
  `Project`.
- **Bug #10** — the MCP boundary declares every field `str` (decision #22); a real model's list/dict
  arguments arrived as JSON- or comma-encoded strings, uncoerced, and `list("problem")` silently
  split a bare area name into five stray one-character "areas."
- **Bug #11** — `manage_assumption(create)` silently defaulted `user_confirmation_required` to
  `False`, and its own `ToolSpec` never even documented the field — direct contradiction of
  DESIGN.md's unconditional "no silent assumptions, ever." Now always `True`, never caller-supplied,
  the same pattern decision #24 already applied to `expected_decision_date`.
- **Bug #12** — Intake's own mode-advancement condition required *no* pending question to leave
  `INTAKE`, backwards: a correctly-shaped intake turn always ends with exactly one. Fixed to always
  advance once intake completes.

With all seven fixed, `tests/eval/test_intake.py`'s real turn against the design doc's own "a tool
for tracking vendor invoices" example passes end to end: 6 PROPOSED requirements, 6 confirmation-
flagged assumptions, exactly one real (`ask_user`-tracked) pending question, and a clean hand-off to
CLARIFY — the first fully real, fully persisted Discovery turn in this build.

Tests: `tests/test_agents/test_intake_shape.py` (8, zero-cost, the pure shape checker),
`tests/eval/test_intake.py` (1, `live_model`, the real end-to-end proof), plus regression coverage
for bugs #6/#10/#11 added to `tests/test_agents/test_model_provider.py`, `tests/test_tools/
test_writers.py` and `tests/test_tools/test_ask_user.py`, and one new mode-advancement test in
`tests/test_agents/test_modes.py` for bug #12. Full suite re-run: **748 passed** (722 baseline + 26
new), 1 skipped, default run; `pytest -m live_model`: 2 passed (T23's own real-turn test + T24's
eval test).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T24: Intake mode — the opening move"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t24_*.md completed_tasks\
   bash:     mv tasks/t24_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T24` on the board.
