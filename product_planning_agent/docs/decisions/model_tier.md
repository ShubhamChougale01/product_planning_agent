# Decision — Which model tier for eval runs

**Date:** 2026-09-30
**Resolves:** T34 · `Plan/Design and Build plan.md` §6.7 open decision #2 · blockers.md decision #4
**Probe script:** `scripts/probe_model_tier.py` (re-runnable)

## Prerequisite this decision depended on

Before this probe could mean anything, `PPA_MODEL_TIER` had to actually reach a real turn.
`ppa/agents/turn.py::_run_one_sdk_turn` (and four sibling call sites — `ppa/agents/modes/change.py`,
`ppa/agents/modes/review.py`, `ppa/agents/subagents/guidance.py`, `ppa/agents/subagents/research.py`)
all constructed a bare `ModelProvider()` rather than `ModelProvider.from_config(...)`, silently
discarding `config/model.yaml` and `PPA_MODEL_TIER` on every real Discovery turn this build has ever
made — every live call from T21 through T33, including all of T33's eval matrix, ran on the default
tier (`primary`) regardless of what anyone set. Fixed in this task, all five sites now call
`ModelProvider.from_config(DEFAULT_CONFIG_PATH)`, verified against the existing `tests/test_agents/
test_model_provider.py` suite (14/14 still pass) and `tests/eval/test_llm_surface_invariant.py` (new,
this task — statically enforces there are exactly these five real call sites, so a sixth added later
without this wiring is caught, not silently repeated).

## Question — Which tier should eval runs use: `cheap`, `primary`, or `deep`?

**Answer: `primary` (Sonnet 5) — the tier every eval run has already been using by accident is also
the right one on purpose.**

One real INTAKE turn (T24's own worked example, "a tool for tracking vendor invoices"), run once per
tier, `PPA_MODEL_TIER` set before each, checked against `ppa.agents.modes.intake.evaluate_intake_shape`
— the same quality bar `tests/eval/test_intake.py` already holds every INTAKE turn to:

| Tier | Model | Elapsed | Cost (equiv., subscription auth) | Shape check |
|---|---|---|---|---|
| `cheap` | claude-haiku-4-5-20251001 | 129.2s | $0.16 | **FAIL** — reply was 25 sentences, not the required "3-6 sentences, not a wall of text" |
| `primary` | claude-sonnet-5 | 107.2s | $0.26 | PASS |
| `deep` | claude-opus-5 | 117.0s | $0.65 | PASS |

**`cheap` loses on every axis that matters here, not just quality.** It was not faster than
`primary` (129.2s vs. 107.2s) and cost only marginally less (~62% of `primary`'s cost) — and it
failed a real, already-established quality bar outright. There is no case in this data for using it
to save wall-clock time on a large eval run; it would need a smaller eval-specific prompt reduction
to be worth it at all, which is out of this task's own scope.

**`deep` passed but at ~2.5x `primary`'s cost for the same shape-check outcome** on this one task.
Nothing here shows `deep` doing anything `primary` doesn't already do correctly — it is not ruled
out for the *hardest* cases (the "adversarial" fixtures, or a genuinely difficult judgment call
`primary` is later shown to get wrong), but there is no evidence yet that it is needed by default.

## Consequence

Eval runs (`tests/eval/`, `pytest -m live_model`, `tests.eval.scorecard`) use `primary`, the shipped
default in `config/model.yaml` — no change to the config. This was already true by accident (the bug
above), and is now true on purpose, with real numbers behind it instead of a guess.

**Caveat, honestly:** this is a single representative probe (n=1 per tier, one task shape — INTAKE),
not an exhaustive study across all eighteen S12.2 cases or all ten fixtures. If a future task needs a
cheaper large-scale run (e.g. hundreds of fixture x persona combinations), re-run this probe against
that specific workload before assuming `cheap`'s quality gap here generalizes — or holds at all once
model versions change.

## How to re-verify

    cd product_planning_agent
    .venv/Scripts/python.exe scripts/probe_model_tier.py

Re-run this if model versions change, if `mode_intake.md`'s own reply-length instruction changes, or
if a future task considers switching the default tier for a large eval run.
