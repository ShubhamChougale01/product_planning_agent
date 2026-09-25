"""The four `manage_*` writer tests (T16). Every Done-when box in
`tasks/t16_manage_writer_tools.md` maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.ledger.audit import read_audit_records
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.results.categories import ErrorCategory
from ppa.tools.discovery_tools import (
    MANAGE_ASSUMPTION_SPEC,
    MANAGE_DECISION_SPEC,
    MANAGE_REQUIREMENT_SPEC,
    MANAGE_UNKNOWN_SPEC,
    manage_assumption,
    manage_decision,
    manage_requirement,
    manage_unknown,
)
from ppa.tools.registry import get, restore, snapshot

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _preserve_registry():
    saved = snapshot()
    yield
    restore(saved)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Writer Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-001", now=NOW)
    base.update(overrides)
    return base


def _create_requirement(project, **overrides) -> str:
    kwargs = dict(
        statement="Users can export invoices as PDF",
        type="functional",
        priority="must",
        confidence="HIGH",
        confidence_basis="user said it directly",
        covers_areas=["jobs"],
        derived_from_answers=["ANS-001"],
    )
    kwargs.update(overrides)
    result = manage_requirement("create", project, **_writer_kwargs(), **kwargs)
    assert result.success is True, result.error
    return result.data["entity_id"]


def _record_answer(project, entity_id="ANS-001") -> None:
    from ppa.ledger.store import append_event_with_id

    append_event_with_id(
        dict(
            ts=NOW, type="answer.recorded", entity_id=entity_id, actor_id="user:shubham", actor_role="user",
            agent_name=None, workflow_state="DISCOVERY", txn_id=None, source="intake",
            reason="seed answer fixture", before=None,
            after=dict(
                id=entity_id, version=1, created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
                created_by="user:shubham", updated_by="user:shubham", history=[],
                status="ANSWERED", text="What does a user do?", why_asked="scoping",
                target_areas=["jobs"], round=1, suggested_options=[], recommended_default=None,
                answer_kind="answered", dont_know_kind=None, answer_text="They export invoices",
                answered_at=NOW.isoformat(),
            ),
            session_id="sess-001",
        ),
        project.events_path,
    )


def _record_unknown(project, **overrides) -> str:
    kwargs = dict(
        question="What accounting system does the client use?",
        area="existing_system",
        why_it_matters="determines the integration approach",
        blocking=True,
        route="USER_DECISION",
        owner_type="user",
    )
    kwargs.update(overrides)
    result = manage_unknown("record", project, **_writer_kwargs(), **kwargs)
    assert result.success is True, result.error
    return result.data["entity_id"]


# ---------------------------------------------------------------------------
# Done when: a requirement with no covers_areas is rejected, actionable.
# ---------------------------------------------------------------------------


def test_requirement_create_without_covers_areas_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement(
        "create", project, **_writer_kwargs(),
        statement="Something", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it",
        covers_areas=[], derived_from_answers=["ANS-001"],
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert "covers_areas" in result.error.description
    assert "problem" in result.error.description  # names a valid key, per the task's own worked example


def test_requirement_create_with_invalid_area_key_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement(
        "create", project, **_writer_kwargs(),
        statement="Something", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it",
        covers_areas=["not_a_real_area"], derived_from_answers=["ANS-001"],
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


# ---------------------------------------------------------------------------
# Done when: a requirement with no provenance link at all is rejected.
# ---------------------------------------------------------------------------


def test_requirement_create_without_any_provenance_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement(
        "create", project, **_writer_kwargs(),
        statement="Something", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it",
        covers_areas=["jobs"],
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert "provenance" in result.error.description.lower() or "derived_from_answers" in result.error.description


def test_requirement_create_with_dangling_provenance_reference_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement(
        "create", project, **_writer_kwargs(),
        statement="Something", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it",
        covers_areas=["jobs"], derived_from_answers=["ANS-999"],
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "DANGLING_REFERENCE"


def test_requirement_create_with_valid_provenance_succeeds(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    entity_id = _create_requirement(project)
    assert entity_id.startswith("REQ-")
    entities = current_entities(project.events_path)
    assert entities[entity_id].status == "PROPOSED"


# ---------------------------------------------------------------------------
# Done when: manage_unknown(record) without both blocking and route is
# rejected.
# ---------------------------------------------------------------------------


def test_unknown_record_without_blocking_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="q", area="problem", why_it_matters="matters", owner_type="user", route="RESEARCH",
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert "blocking" in result.error.description


def test_unknown_record_without_route_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="q", area="problem", why_it_matters="matters", owner_type="user", blocking=True,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert "route" in result.error.description


def test_unknown_record_with_blocking_false_is_not_treated_as_missing(tmp_path):
    """`blocking=False` is a real, meaningful value — it must never be
    confused with "not supplied" the way a bare truthiness check would."""

    project = _make_project(tmp_path)
    result = manage_unknown(
        "record", project, **_writer_kwargs(),
        question="q", area="problem", why_it_matters="matters", owner_type="user",
        blocking=False, route="OPTIONAL",
    )
    assert result.success is True


# ---------------------------------------------------------------------------
# Done when: manage_decision(defer) without its required fields is rejected
# — expected_decision_date is computed automatically (decision #21/#24 in
# blockers.md), never caller-supplied, so it is verified as *present and
# correct on success*, not as a field whose absence is itself rejectable.
# ---------------------------------------------------------------------------


def _open_decision(project, **overrides) -> str:
    kwargs = dict(question="Which payment processor?", owner="user:jane", owner_type="user")
    kwargs.update(overrides)
    result = manage_decision("open", project, **_writer_kwargs(), **kwargs)
    assert result.success is True, result.error
    return result.data["entity_id"]


def test_decision_defer_without_defer_reason_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    dec_id = _open_decision(project)
    result = manage_decision(
        "defer", project, **_writer_kwargs(), entity_id=dec_id, owner="user:jane", owner_type="user",
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert "defer_reason" in result.error.description


def test_decision_defer_without_owner_or_owner_type_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    dec_id = _open_decision(project)
    result = manage_decision(
        "defer", project, **_writer_kwargs(), entity_id=dec_id, defer_reason="waiting on finance",
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


def test_decision_defer_computes_expected_decision_date_via_t12_rule(tmp_path):
    project = _make_project(tmp_path)
    dec_id = _open_decision(project, blocking=True, affects="architecture")
    result = manage_decision(
        "defer", project, **_writer_kwargs(), entity_id=dec_id,
        defer_reason="waiting on finance team", owner="user:jane", owner_type="user",
    )
    assert result.success is True, result.error
    entities = current_entities(project.events_path)
    decision = entities[dec_id]
    assert decision.status == "DECIDE_LATER"
    assert decision.expected_decision_date is not None
    # blocking + architecture -> now + 3 days, per EXPECTED_DECISION_DATE_RULE.
    assert (decision.expected_decision_date - NOW).days == 3


def test_decision_decide_requires_chosen_option_and_rationale(tmp_path):
    project = _make_project(tmp_path)
    dec_id = _open_decision(project)
    result = manage_decision("decide", project, **_writer_kwargs(), entity_id=dec_id)
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION

    result = manage_decision(
        "decide", project, **_writer_kwargs(), entity_id=dec_id,
        chosen_option="Stripe", rationale="already used elsewhere in the org",
    )
    assert result.success is True, result.error
    entities = current_entities(project.events_path)
    assert entities[dec_id].status == "DECIDED"
    assert entities[dec_id].decided_at is not None


# ---------------------------------------------------------------------------
# Done when: confirming a requirement whose area has an open blocking
# unknown is rejected as semantic.
# ---------------------------------------------------------------------------


def test_requirement_confirm_blocked_by_open_blocking_unknown(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    req_id = _create_requirement(project, covers_areas=["existing_system"])
    _record_unknown(project, area="existing_system")

    result = manage_requirement("confirm", project, **_writer_kwargs(), entity_id=req_id)
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "AREA_BLOCKED"


def test_requirement_confirm_succeeds_once_unknown_is_resolved(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    req_id = _create_requirement(project, covers_areas=["existing_system"])
    unk_id = _record_unknown(project, area="existing_system")

    resolve_result = manage_unknown("resolve", project, **_writer_kwargs(), entity_id=unk_id)
    assert resolve_result.success is True, resolve_result.error

    confirm_result = manage_requirement("confirm", project, **_writer_kwargs(), entity_id=req_id)
    assert confirm_result.success is True, confirm_result.error
    entities = current_entities(project.events_path)
    assert entities[req_id].status == "CONFIRMED"


def test_requirement_confirm_not_blocked_by_unknown_in_a_different_area(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    req_id = _create_requirement(project, covers_areas=["jobs"])
    _record_unknown(project, area="existing_system")

    result = manage_requirement("confirm", project, **_writer_kwargs(), entity_id=req_id)
    assert result.success is True, result.error


# ---------------------------------------------------------------------------
# Done when: every write emits exactly one event and one audit record.
# ---------------------------------------------------------------------------


def test_create_emits_exactly_one_event_and_one_audit_record(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)

    events_before = len(list(project.events_path.open("r", encoding="utf-8"))) if project.events_path.exists() else 0
    audit_before = len(read_audit_records(project.audit_path))

    _create_requirement(project)

    events_after = len(list(project.events_path.open("r", encoding="utf-8")))
    audit_after = read_audit_records(project.audit_path)

    assert events_after - events_before == 1
    assert len(audit_after) - audit_before == 1
    assert audit_after[-1].tool == "manage_requirement"
    assert audit_after[-1].result.success is True


def test_rejection_still_emits_exactly_one_audit_record_and_zero_events(tmp_path):
    project = _make_project(tmp_path)

    events_before = len(list(project.events_path.open("r", encoding="utf-8")))
    audit_before = len(read_audit_records(project.audit_path))

    result = manage_requirement(
        "create", project, **_writer_kwargs(), statement="x", type="functional",
        priority="must", confidence="HIGH", confidence_basis="y", covers_areas=[],
    )
    assert result.success is False

    events_after = len(list(project.events_path.open("r", encoding="utf-8")))
    audit_after = read_audit_records(project.audit_path)

    assert events_after == events_before
    assert len(audit_after) - audit_before == 1
    assert audit_after[-1].result.success is False
    assert audit_after[-1].result.category == ErrorCategory.VALIDATION


# ---------------------------------------------------------------------------
# Done when: every write is idempotent under a repeated idem_key.
# ---------------------------------------------------------------------------


def test_create_is_idempotent_under_a_repeated_idem_key(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)

    first = manage_requirement(
        "create", project, **_writer_kwargs(idem_key="req-create-1"),
        statement="Users can export invoices as PDF", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it directly",
        covers_areas=["jobs"], derived_from_answers=["ANS-001"],
    )
    assert first.success is True

    second = manage_requirement(
        "create", project, **_writer_kwargs(idem_key="req-create-1"),
        statement="Users can export invoices as PDF", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it directly",
        covers_areas=["jobs"], derived_from_answers=["ANS-001"],
    )
    assert second.success is True
    assert second.data["entity_id"] == first.data["entity_id"]
    assert second.data["replayed"] is True

    entities = current_entities(project.events_path)
    assert sum(1 for eid in entities if eid.startswith("REQ-")) == 1


# ---------------------------------------------------------------------------
# Done when: free text passes through secret scanning before the event is
# built.
# ---------------------------------------------------------------------------


def test_requirement_statement_is_secret_scanned_before_write(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    leaky = "connects via postgres://admin:hunter2@db.internal:5432/prod"
    entity_id = _create_requirement(project, statement=leaky)
    entities = current_entities(project.events_path)
    assert "hunter2" not in entities[entity_id].statement
    assert "[REDACTED:credential]" in entities[entity_id].statement


# ---------------------------------------------------------------------------
# General coverage across the other operations and entity types.
# ---------------------------------------------------------------------------


def test_requirement_revise_updates_fields_and_records_history(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    req_id = _create_requirement(project)

    result = manage_requirement(
        "revise", project, **_writer_kwargs(), entity_id=req_id,
        statement="Users can export invoices as PDF or CSV", change_reason="clarified with the user",
    )
    assert result.success is True, result.error
    entities = current_entities(project.events_path)
    revised = entities[req_id]
    assert revised.statement == "Users can export invoices as PDF or CSV"
    assert revised.version == 2
    assert any(h.field == "statement" for h in revised.history)


def test_requirement_reject_and_supersede_are_terminal(tmp_path):
    project = _make_project(tmp_path)
    _record_answer(project)
    req_id = _create_requirement(project)

    result = manage_requirement("reject", project, **_writer_kwargs(), entity_id=req_id, change_reason="not needed")
    assert result.success is True, result.error

    again = manage_requirement("confirm", project, **_writer_kwargs(), entity_id=req_id)
    assert again.success is False
    assert again.error.category == ErrorCategory.BUSINESS
    assert again.error.code == "ILLEGAL_TRANSITION"


def test_requirement_unknown_operation_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement("delete", project, **_writer_kwargs(), entity_id="REQ-001")
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "UNKNOWN_OPERATION"


def test_assumption_create_confirm_and_modify(tmp_path):
    project = _make_project(tmp_path)
    result = manage_assumption(
        "create", project, **_writer_kwargs(),
        statement="Single currency (USD) for v1", reason="no mention of multi-currency in the seed",
        impact="MEDIUM", confidence="MEDIUM", confidence_basis="strongly implied by scope",
    )
    assert result.success is True, result.error
    asm_id = result.data["entity_id"]

    modify_result = manage_assumption(
        "modify", project, **_writer_kwargs(), entity_id=asm_id, impact="HIGH",
    )
    assert modify_result.success is True, modify_result.error

    confirm_result = manage_assumption("confirm", project, **_writer_kwargs(), entity_id=asm_id)
    assert confirm_result.success is True, confirm_result.error
    entities = current_entities(project.events_path)
    confirmed = entities[asm_id]
    assert confirmed.status == "CONFIRMED"
    assert confirmed.confirmed_at is not None
    assert confirmed.confirmed_by == "user:shubham"


def test_unknown_classify_resolve_and_convert(tmp_path):
    project = _make_project(tmp_path)
    unk_id = _record_unknown(project)

    classify_result = manage_unknown("classify", project, **_writer_kwargs(), entity_id=unk_id, route="RESEARCH")
    assert classify_result.success is True, classify_result.error
    entities = current_entities(project.events_path)
    assert entities[unk_id].route == "RESEARCH"

    dec_id = _open_decision(project)
    convert_result = manage_unknown("convert", project, **_writer_kwargs(), entity_id=unk_id, converted_to=dec_id)
    assert convert_result.success is True, convert_result.error
    entities = current_entities(project.events_path)
    assert entities[unk_id].status == "CONVERTED"
    assert entities[unk_id].converted_to == dec_id


def test_unknown_convert_to_a_nonexistent_entity_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    unk_id = _record_unknown(project)
    result = manage_unknown("convert", project, **_writer_kwargs(), entity_id=unk_id, converted_to="DEC-999")
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "DANGLING_REFERENCE"


def test_operation_on_missing_entity_id_returns_not_found(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement("confirm", project, **_writer_kwargs(), entity_id="REQ-999")
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# ToolSpec registration completeness.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,spec",
    [
        ("manage_requirement", MANAGE_REQUIREMENT_SPEC),
        ("manage_assumption", MANAGE_ASSUMPTION_SPEC),
        ("manage_decision", MANAGE_DECISION_SPEC),
        ("manage_unknown", MANAGE_UNKNOWN_SPEC),
    ],
)
def test_writer_toolspec_is_registered_and_complete(tool_name, spec):
    registered = get(tool_name)
    assert registered.spec is spec
    assert len(registered.spec.examples) >= 2
    assert len(registered.spec.use_when) >= 2
    assert len(registered.spec.do_not_use_when) >= 2
    assert "discovery" in registered.owner_agents
