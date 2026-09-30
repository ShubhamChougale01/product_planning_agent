"""The eighteen S12.2 cases (`tasks/t34_eval_suite_and_baseline.md`).

Cases 1, 3, 13 and 14 make a claim about real model behavior (which tool a
live turn picks, how it disambiguates, how it routes a real "I don't know")
and are marked `live_model` — excluded from the default `pytest` run,
proven directly against `ppa.agents.discovery.DiscoveryAgent`, the same way
every other live proof in this package already works.

The other fourteen prove a case's own contract directly against the real
production code path the design already builds it on (dispatch, retry,
escalation, approval, the five validation layers) — no model call, matching
this codebase's own established discipline (T32's transaction/retry/
escalation proofs) of never routing a deterministic-policy claim through a
model just because the wider system sometimes involves one.

`ALL_CASE_MODULES` is the scorecard command's own case inventory —
`tests/eval/scorecard.py` imports each module's `run_case(tmp_path) ->
CaseOutcome` function listed here in order.
"""

from __future__ import annotations

CASE_MODULE_NAMES: tuple[str, ...] = (
    "tests.eval.cases.case_01_correct_tool_selection",
    "tests.eval.cases.case_02_wrong_tool_attempt",
    "tests.eval.cases.case_03_ambiguous_description",
    "tests.eval.cases.case_04_validation_error",
    "tests.eval.cases.case_05_transient_failure",
    "tests.eval.cases.case_06_permission_failure",
    "tests.eval.cases.case_07_business_workflow_failure",
    "tests.eval.cases.case_08_empty_successful_result",
    "tests.eval.cases.case_09_partial_subagent_failure",
    "tests.eval.cases.case_10_retry_exhaustion",
    "tests.eval.cases.case_11_invalid_state_transition",
    "tests.eval.cases.case_12_linear_creation_before_approval",
    "tests.eval.cases.case_13_i_dont_know",
    "tests.eval.cases.case_14_decide_later",
    "tests.eval.cases.case_15_requirement_version_change",
    "tests.eval.cases.case_16_secret_pasted_into_answer",
    "tests.eval.cases.case_17_irreversible_action_without_approval",
    "tests.eval.cases.case_18_approval_replay_scope_mismatch",
)

LIVE_CASE_MODULE_NAMES: frozenset[str] = frozenset({
    "tests.eval.cases.case_01_correct_tool_selection",
    "tests.eval.cases.case_03_ambiguous_description",
    "tests.eval.cases.case_13_i_dont_know",
    "tests.eval.cases.case_14_decide_later",
})
