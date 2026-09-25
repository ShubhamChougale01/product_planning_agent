"""Validation layer wiring tests (T19). Every Done-when box in
`tasks/t19_validation_layer_wiring.md` maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.ledger.digest import read_digest
from ppa.ledger.materialize import current_entities
from ppa.ledger.models import EntityType
from ppa.ledger.project import create_project
from ppa.results.categories import ErrorCategory
from ppa.tools.discovery_tools import manage_requirement, manage_unknown
from ppa.tools.hooks import pre_tool_use
from ppa.tools.spec import ToolSpec
from ppa.validation import infer_validation_layer, permission, schema, semantic, workflow
from ppa.validation.consistency import check_transition

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)

_SPEC = ToolSpec(
    name="manage_requirement",
    purpose="test spec",
    inputs={"a": "str, a field"},
    required=["a"],
    optional=[],
    formats={},
    returns="{ok: bool}",
    examples=["manage_requirement(a='x')", "manage_requirement(a='y')"],
    edge_cases=["a is empty"],
    limitations=["test only"],
    use_when=["condition one", "condition two"],
    do_not_use_when=["condition three", "condition four"],
    related_tools={"other": "does something else"},
)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Layer Order Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


# ---------------------------------------------------------------------------
# Done when: layer numbering in code comments matches §2.13 exactly.
# ---------------------------------------------------------------------------


def test_hooks_module_docstring_states_layers_1_through_3_in_order():
    import ppa.tools.hooks as hooks_module

    doc = hooks_module.__doc__
    assert doc.index("1  Permission") < doc.index("2  Schema") < doc.index("3  Workflow")


@pytest.mark.parametrize(
    "module_name,expected_layer",
    [
        ("permission", "permission"),
        ("schema", "schema"),
        ("workflow", "workflow"),
        ("semantic", "semantic"),
        ("consistency", "consistency"),
    ],
)
def test_each_validation_module_declares_its_own_layer_name(module_name, expected_layer):
    import importlib

    module = importlib.import_module(f"ppa.validation.{module_name}")
    assert module.LAYER == expected_layer


# ---------------------------------------------------------------------------
# Done when: each layer has a test that fails at that layer and no
# earlier.
# ---------------------------------------------------------------------------


def test_layer_1_permission_fails_alone():
    result = permission.check("manage_requirement", "delivery")
    assert result is not None
    assert result.error.category == ErrorCategory.PERMISSION
    assert result.error.context["validation_layer_failed"] == "permission"

    # A granted agent clears layer 1 with the exact same call shape.
    assert permission.check("manage_requirement", "discovery") is None


def test_layer_2_schema_fails_alone():
    result = schema.check(_SPEC, {})
    assert result is not None
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.context["validation_layer_failed"] == "schema"

    assert schema.check(_SPEC, {"a": "x"}) is None


def test_layer_3_workflow_fails_alone():
    result = workflow.check("manage_requirement", "PLAN_APPROVED")
    assert result is not None
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.context["validation_layer_failed"] == "workflow"

    assert workflow.check("manage_requirement", "DISCOVERY") is None


def test_layer_4_semantic_fails_alone(tmp_path):
    project = _make_project(tmp_path)
    result = manage_requirement(
        "create", project, actor_id="user:shubham", session_id="sess-001", now=NOW,
        statement="Needs the existing system integration", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it", covers_areas=["existing_system"],
        derived_from_answers=["ANS-001"],
    )
    # Bypass the provenance dangling-ref check with a real answer record so
    # only the semantic layer is what fails below.
    from ppa.ledger.store import append_event_with_id

    append_event_with_id(
        dict(
            ts=NOW, type="answer.recorded", entity_id="ANS-001", actor_id="user:shubham", actor_role="user",
            agent_name=None, workflow_state="DISCOVERY", txn_id=None, source="fixture", reason="fixture answer",
            before=None,
            after=dict(
                id="ANS-001", version=1, created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
                created_by="user:shubham", updated_by="user:shubham", history=[], status="ANSWERED",
                text="q", why_asked="w", target_areas=[], round=1, suggested_options=[],
                recommended_default=None, answer_kind="answered", dont_know_kind=None,
                answer_text="a", answered_at=NOW.isoformat(),
            ),
            session_id="sess-001",
        ),
        project.events_path,
    )
    result = manage_requirement(
        "create", project, actor_id="user:shubham", session_id="sess-001", now=NOW,
        statement="Needs the existing system integration", type="functional", priority="must",
        confidence="HIGH", confidence_basis="user said it", covers_areas=["existing_system"],
        derived_from_answers=["ANS-001"],
    )
    assert result.success is True, result.error
    req_id = result.data["entity_id"]

    manage_unknown(
        "record", project, actor_id="user:shubham", session_id="sess-001", now=NOW,
        question="what accounting system?", area="existing_system", why_it_matters="scope",
        blocking=True, route="USER_DECISION", owner_type="user",
    )

    confirm_result = manage_requirement("confirm", project, actor_id="user:shubham", session_id="sess-001", now=NOW, entity_id=req_id)
    assert confirm_result.success is False
    assert confirm_result.error.category == ErrorCategory.BUSINESS
    assert confirm_result.error.code == "AREA_BLOCKED"
    assert infer_validation_layer(confirm_result.error) == "semantic"

    # Registered so ppa.validation.semantic can run it directly too.
    entities = current_entities(project.events_path)
    direct = semantic.check("manage_requirement.confirm", entities, entities[req_id], {})
    assert direct is not None
    assert direct.error.code == "AREA_BLOCKED"


def test_layer_5_consistency_fails_alone():
    result = check_transition(EntityType.REQUIREMENT, "REJECTED", "CONFIRMED")
    assert result is not None
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "ILLEGAL_TRANSITION"
    assert infer_validation_layer(result.error) == "consistency"

    assert check_transition(EntityType.REQUIREMENT, "PROPOSED", "CONFIRMED") is None


# ---------------------------------------------------------------------------
# Done when: validation_layer_failed appears in the audit record for every
# rejection.
# ---------------------------------------------------------------------------


def test_validation_layer_failed_appears_in_the_audit_record_for_a_schema_rejection(tmp_path):
    from ppa.ledger.audit import read_audit_records

    project = _make_project(tmp_path)
    manage_requirement(
        "create", project, actor_id="user:shubham", session_id="sess-001", now=NOW,
        statement="x", type="functional", priority="must", confidence="HIGH",
        confidence_basis="y", covers_areas=[],
    )
    records = read_audit_records(project.audit_path)
    assert len(records) == 1
    assert records[-1].validation_layer_failed == "schema"


def test_validation_layer_failed_appears_for_a_consistency_rejection(tmp_path):
    from ppa.ledger.audit import read_audit_records
    from ppa.ledger.store import append_event_with_id

    project = _make_project(tmp_path)
    append_event_with_id(
        dict(
            ts=NOW, type="requirement.created", entity_id=None, actor_id="user:shubham", actor_role="user",
            agent_name=None, workflow_state="DISCOVERY", txn_id=None, source="fixture", reason="fixture",
            before=None,
            after=dict(
                id="PENDING", version=1, created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
                created_by="user:shubham", updated_by="user:shubham", history=[], confidence="HIGH",
                confidence_basis="basis", status="REJECTED", statement="x", type="functional",
                covers_areas=["jobs"], derived_from_answers=[], depends_on_assumptions=[],
                depends_on_decisions=[], priority="must", needs_user_confirmation=False, custom_fields={},
            ),
            session_id="sess-001",
        ),
        project.events_path, id_prefix="REQ",
    )
    entities = current_entities(project.events_path)
    req_id = next(iter(entities))

    result = manage_requirement("confirm", project, actor_id="user:shubham", session_id="sess-001", now=NOW, entity_id=req_id)
    assert result.success is False
    assert result.error.code == "ILLEGAL_TRANSITION"

    records = read_audit_records(project.audit_path)
    assert records[-1].validation_layer_failed == "consistency"


def test_validation_layer_failed_is_none_for_a_permission_style_approval_rejection(tmp_path):
    """Approval-gate rejections are a sixth, separate gate (§2.19.2) — they
    correctly report no `validation_layer_failed`, never a forced guess at
    one of the five."""

    from ppa.ledger.audit import read_audit_records
    from ppa.tools.delivery_tools import manage_linear_issue

    project = _make_project(tmp_path)
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=["STORY-001"], now=NOW,
    )
    assert result.success is False
    assert result.error.code == "APPROVAL_REQUIRED"

    records = read_audit_records(project.audit_path)
    assert records[-1].validation_layer_failed is None


# ---------------------------------------------------------------------------
# Done when: a call that would fail at multiple layers reports the
# earliest one.
# ---------------------------------------------------------------------------


def test_pre_tool_use_reports_the_earliest_failing_layer():
    # Fails permission (delivery isn't granted manage_requirement) AND
    # schema (missing the required "a" field) at once -> permission wins.
    result = pre_tool_use("manage_requirement", {}, _SPEC, agent_id="delivery", workflow_state="DISCOVERY")
    assert result is not None
    assert result.error.category == ErrorCategory.PERMISSION
    assert result.error.context["validation_layer_failed"] == "permission"


def test_pre_tool_use_reports_schema_when_permission_already_passed():
    # Granted, but missing the required field, and also in an illegal
    # workflow state -> schema (layer 2) wins over workflow (layer 3).
    result = pre_tool_use("manage_requirement", {}, _SPEC, agent_id="discovery", workflow_state="PLAN_APPROVED")
    assert result is not None
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.context["validation_layer_failed"] == "schema"


def test_pre_tool_use_passes_when_all_three_layers_clear():
    result = pre_tool_use("manage_requirement", {"a": "x"}, _SPEC, agent_id="discovery", workflow_state="DISCOVERY")
    assert result is None


# ---------------------------------------------------------------------------
# Done when: bypassing the tool layer cannot mutate state — a direct file
# write and the digest stays unchanged.
# ---------------------------------------------------------------------------


def test_a_direct_entities_file_write_never_affects_the_digest(tmp_path):
    project = _make_project(tmp_path)
    before = read_digest(project, now=NOW)

    entities_dir = project.planning_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    (entities_dir / "REQ-999.json").write_text(
        '{"id": "REQ-999", "version": 1, "created_at": "2026-01-01T00:00:00Z", '
        '"updated_at": "2026-01-01T00:00:00Z", "created_by": "attacker", "updated_by": "attacker", '
        '"history": [], "confidence": "HIGH", "confidence_basis": "forged", "status": "CONFIRMED", '
        '"statement": "a smuggled requirement", "type": "functional", "covers_areas": ["jobs"], '
        '"derived_from_answers": [], "depends_on_assumptions": [], "depends_on_decisions": [], '
        '"priority": "must", "needs_user_confirmation": false, "custom_fields": {}}',
        encoding="utf-8",
    )

    after = read_digest(project, now=NOW)
    assert after == before
    assert "REQ-999" not in after
    assert "smuggled" not in after

    entities = current_entities(project.events_path)
    assert "REQ-999" not in entities
