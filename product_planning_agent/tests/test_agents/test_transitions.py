"""Global workflow state machine tests (T20). Every transition-related
Done-when box in `tasks/t20_agent_protocol_and_workflow.md` maps to at
least one test here.
"""

from __future__ import annotations

import inspect

import pytest
import yaml

import ppa.workflow.machine as machine
from ppa.results.categories import ErrorCategory


# ---------------------------------------------------------------------------
# Done when: the transition table is data; no workflow conditionals in
# Python.
# ---------------------------------------------------------------------------


def test_transitions_are_loaded_from_the_yaml_file_not_hardcoded():
    on_disk = yaml.safe_load(machine._TRANSITIONS_PATH.read_text(encoding="utf-8"))
    assert machine.STATES == on_disk["states"]
    assert machine._RAW_TRANSITIONS == on_disk["transitions"]


def test_validate_transition_body_has_no_if_elif_chain_over_state_names():
    """`validate_transition` and `legal_targets` do table lookups only —
    grepping their own source for literal state-name string comparisons
    (beyond the generic `frm == to` no-op check) would mean a conditional
    crept back in."""

    source = inspect.getsource(machine.validate_transition) + inspect.getsource(machine.legal_targets)
    for state in machine.STATES:
        assert f'"{state}"' not in source
        assert f"'{state}'" not in source


# ---------------------------------------------------------------------------
# Done when: an illegal transition is rejected naming the rule that
# blocked it.
# ---------------------------------------------------------------------------


def test_illegal_transition_raises_naming_frm_to_and_legal_targets():
    with pytest.raises(machine.IllegalWorkflowTransition) as exc_info:
        machine.validate_transition("DISCOVERY", "COMPLETE")
    message = str(exc_info.value)
    assert "DISCOVERY" in message
    assert "COMPLETE" in message
    assert "DISCOVERY_VALIDATED" in message  # the actual legal target, named


def test_same_state_transition_is_always_legal():
    machine.validate_transition("DISCOVERY", "DISCOVERY")  # must not raise


def test_check_returns_a_business_tool_result_tagged_workflow_layer():
    result = machine.check("DISCOVERY", "COMPLETE")
    assert result is not None
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "ILLEGAL_WORKFLOW_TRANSITION"
    assert result.error.context["validation_layer_failed"] == "workflow"


def test_check_returns_none_for_a_legal_transition():
    assert machine.check("DISCOVERY", "DISCOVERY_VALIDATED") is None


def test_condition_for_returns_the_named_condition():
    assert machine.condition_for("DISCOVERY", "DISCOVERY_VALIDATED") == "validate_discovery_state"
    assert machine.condition_for("DISCOVERY", "COMPLETE") is None


# ---------------------------------------------------------------------------
# Done when: CHANGE_REQUESTED is reachable from every state.
# ---------------------------------------------------------------------------


def test_change_requested_is_reachable_from_every_state():
    assert machine.is_reachable_from_every_state("CHANGE_REQUESTED") is True


@pytest.mark.parametrize("state", machine.STATES)
def test_change_requested_is_a_legal_target_from_each_individual_state(state):
    if state == "CHANGE_REQUESTED":
        pytest.skip("a state is not its own transition target")
    assert "CHANGE_REQUESTED" in machine.legal_targets(state)


def test_completion_is_not_reachable_from_every_state_a_negative_control():
    """A sanity check on `is_reachable_from_every_state` itself — it must
    say `False` for a state that plainly isn't universally reachable, or
    the CHANGE_REQUESTED assertion above would be vacuous."""

    assert machine.is_reachable_from_every_state("COMPLETE") is False


# ---------------------------------------------------------------------------
# v1 walks DISCOVERY -> DISCOVERY_VALIDATED and stops; later states are
# declared, not yet reachable in practice.
# ---------------------------------------------------------------------------


def test_v1_legal_path_is_discovery_to_discovery_validated():
    assert machine.legal_targets("DISCOVERY") == frozenset({"DISCOVERY_VALIDATED", "CHANGE_REQUESTED"})


def test_planning_and_delivery_states_are_declared_but_unreachable_from_discovery_validated_without_advancing():
    # DISCOVERY_VALIDATED -> PLANNING is a legal *move* (the table allows
    # it); whether the Orchestrator actually takes it in v1 is a separate,
    # runtime question this table does not answer on its own (T21).
    assert "PLANNING" in machine.legal_targets("DISCOVERY_VALIDATED")
