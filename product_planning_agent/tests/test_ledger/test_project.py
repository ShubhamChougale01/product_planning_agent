"""Project lifecycle, audit log and git tests (T08). Every Done-when box in
tasks/t08_project_lifecycle_audit_git.md maps to at least one test here.
"""

from __future__ import annotations

import re
import subprocess

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

from ppa.config.profiles import UserProfile
from ppa.ledger import gitops
from ppa.ledger.audit import AuditResult, hash_inputs, read_audit_records, record_audit
from ppa.ledger.events import Event, EventType
from ppa.ledger.project import (
    VERBATIM_STORAGE_NOTICE,
    create_project,
    list_projects,
    open_project,
)
from ppa.results.categories import ErrorCategory


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _git(repo_dir, *args) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo_dir), check=True, capture_output=True, text=True
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Done when: two projects coexist with fully independent ledgers.
# ---------------------------------------------------------------------------


def test_two_projects_coexist_with_independent_ledgers(tmp_path):
    projects_root = tmp_path / "projects"
    alpha = create_project("Alpha Project", "users need to log in", _profile(), projects_root=projects_root)
    beta = create_project("Beta Project", "users need to export data", _profile(), projects_root=projects_root)

    assert alpha.path != beta.path
    assert alpha.events_path.exists()
    assert beta.events_path.exists()

    alpha_lines = alpha.events_path.read_text(encoding="utf-8").splitlines()
    beta_lines = beta.events_path.read_text(encoding="utf-8").splitlines()
    assert len(alpha_lines) == 1
    assert len(beta_lines) == 1
    assert "Alpha Project" in alpha_lines[0]
    assert "Beta Project" not in alpha_lines[0]
    assert "Beta Project" in beta_lines[0]
    assert "Alpha Project" not in beta_lines[0]

    listed = {p.slug for p in list_projects(projects_root=projects_root)}
    assert listed == {"alpha-project", "beta-project"}


def test_open_project_round_trips_what_create_project_wrote(tmp_path):
    projects_root = tmp_path / "projects"
    created = create_project(
        "Checkout Revamp", "seed requirement", _profile(role="product"), projects_root=projects_root
    )

    reopened = open_project("checkout-revamp", projects_root=projects_root)

    assert reopened.slug == created.slug
    assert reopened.name == created.name
    assert reopened.profile == created.profile
    assert reopened.workflow_state == created.workflow_state
    assert reopened.created_at == created.created_at


def test_create_project_twice_with_same_name_raises(tmp_path):
    projects_root = tmp_path / "projects"
    create_project("Dup", "seed", _profile(), projects_root=projects_root)
    try:
        create_project("Dup", "seed again", _profile(), projects_root=projects_root)
        assert False, "expected FileExistsError"
    except FileExistsError:
        pass


# ---------------------------------------------------------------------------
# Done when: a freshly created project has zero git remotes — assert it.
# ---------------------------------------------------------------------------


def test_freshly_created_project_has_zero_git_remotes(tmp_path):
    project = create_project("No Remote", "seed", _profile(), projects_root=tmp_path / "projects")
    assert gitops.list_remotes(project.path) == []


def test_gitignore_excludes_local_and_scratch(tmp_path):
    project = create_project("Ignore Test", "seed", _profile(), projects_root=tmp_path / "projects")
    gitignore = (project.path / ".gitignore").read_text(encoding="utf-8")
    assert "*.local.*" in gitignore
    assert "scratch/" in gitignore


# ---------------------------------------------------------------------------
# Done when: git log --oneline reads as a comprehensible planning narrative.
# ---------------------------------------------------------------------------


def test_git_log_reads_as_a_comprehensible_planning_narrative(tmp_path):
    project = create_project("Narrative", "seed", _profile(), projects_root=tmp_path / "projects")

    log_after_creation = _git(project.path, "log", "--oneline")
    assert "scaffold" in log_after_creation
    assert "project created" in log_after_creation

    events = [
        Event(
            event_id="EVT-000002",
            ts=project.created_at,
            type=EventType.REQUIREMENT_CREATED,
            entity_id="REQ-001",
            actor_id="agent:discovery",
            actor_role="agent",
            agent_name="DiscoveryAgent",
            workflow_state="DISCOVERY",
            txn_id=None,
            source="intake",
            reason="seed requirement interpreted",
            before=None,
            after={"id": "REQ-001"},
            session_id="sess-001",
        ),
        Event(
            event_id="EVT-000003",
            ts=project.created_at,
            type=EventType.REQUIREMENT_CREATED,
            entity_id="REQ-002",
            actor_id="agent:discovery",
            actor_role="agent",
            agent_name="DiscoveryAgent",
            workflow_state="DISCOVERY",
            txn_id=None,
            source="intake",
            reason="second requirement",
            before=None,
            after={"id": "REQ-002"},
            session_id="sess-001",
        ),
        Event(
            event_id="EVT-000004",
            ts=project.created_at,
            type=EventType.ASSUMPTION_CREATED,
            entity_id="ASM-001",
            actor_id="agent:discovery",
            actor_role="agent",
            agent_name="DiscoveryAgent",
            workflow_state="DISCOVERY",
            txn_id=None,
            source="intake",
            reason="assumption made",
            before=None,
            after={"id": "ASM-001"},
            session_id="sess-001",
        ),
        Event(
            event_id="EVT-000005",
            ts=project.created_at,
            type=EventType.UNKNOWN_RESOLVED,
            entity_id="UNK-004",
            actor_id="user:shubham",
            actor_role="user",
            agent_name=None,
            workflow_state="DISCOVERY",
            txn_id=None,
            source="clarify",
            reason="user answered directly",
            before=None,
            after={"id": "UNK-004"},
            session_id="sess-001",
        ),
    ]
    for event in events:
        project.events_path.write_text(
            project.events_path.read_text(encoding="utf-8") + event.model_dump_json() + "\n",
            encoding="utf-8",
        )

    message = gitops.commit_turn(project.path, events, round_number=3)
    assert message == "round 3: +2 requirements, +1 assumption, resolved UNK-004"

    log = _git(project.path, "log", "--oneline")
    assert "round 3: +2 requirements, +1 assumption, resolved UNK-004" in log
    lines = [line for line in log.splitlines() if line.strip()]
    assert len(lines) == 3


def test_commit_turn_with_no_ledger_files_is_a_no_op(tmp_path):
    project_dir = tmp_path / "bare"
    project_dir.mkdir()
    gitops.git_init(project_dir)
    assert gitops.commit_turn(project_dir, []) is None


# ---------------------------------------------------------------------------
# Done when: the verbatim-storage notice is shown on `ppa new`.
# ---------------------------------------------------------------------------


def test_verbatim_storage_notice_text_is_stable():
    assert "verbatim" in VERBATIM_STORAGE_NOTICE
    assert "local git repo" in VERBATIM_STORAGE_NOTICE
    assert "add a remote only if" in VERBATIM_STORAGE_NOTICE


def test_ppa_new_shows_the_verbatim_storage_notice(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["new", "CLI Project", "--seed", "users need to log in"],
    )

    assert result.exit_code == 0, result.output
    # Rich wraps long lines to the console width (re-emitting color codes at
    # each wrap point), so strip ANSI and collapse whitespace before comparing.
    flattened_output = " ".join(_ANSI_ESCAPE.sub("", result.output).split())
    assert " ".join(VERBATIM_STORAGE_NOTICE.split()) in flattened_output
    assert (tmp_path / "projects" / "cli-project" / ".planning" / "events.ndjson").exists()


# ---------------------------------------------------------------------------
# Done when: a rejected tool call appears in audit.ndjson and leaves
# events.ndjson untouched.
# ---------------------------------------------------------------------------


def test_rejected_tool_call_appears_in_audit_and_leaves_events_untouched(tmp_path):
    project = create_project("Audit Test", "seed", _profile(), projects_root=tmp_path / "projects")
    events_before = project.events_path.read_text(encoding="utf-8")

    record_audit(
        agent="DiscoveryAgent",
        tool="manage_requirement",
        operation="reject",
        workflow_state="DISCOVERY",
        inputs={"statement": "users need SSO"},
        reason="permission denied: tool not granted in this workflow state",
        result=AuditResult(success=False, category=ErrorCategory.PERMISSION, code="WRONG_STATE"),
        path=project.audit_path,
        ledger_version_before=1,
        ledger_version_after=1,
    )

    assert project.events_path.read_text(encoding="utf-8") == events_before

    records = read_audit_records(project.audit_path)
    assert len(records) == 1
    assert records[0].operation == "reject"
    assert records[0].result.success is False
    assert records[0].result.category == ErrorCategory.PERMISSION
    assert records[0].ledger_version_before == records[0].ledger_version_after == 1


def test_audit_result_requires_category_and_code_on_failure():
    try:
        AuditResult(success=False)
        assert False, "expected a ValueError"
    except ValueError:
        pass


def test_audit_result_forbids_category_and_code_on_success():
    try:
        AuditResult(success=True, category=ErrorCategory.PERMISSION, code="X")
        assert False, "expected a ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Done when: no tool input value is recoverable from the audit log — only
# hashes and pointers.
# ---------------------------------------------------------------------------


def test_no_tool_input_value_is_recoverable_from_the_audit_log(tmp_path):
    project = create_project("Secret Test", "seed", _profile(), projects_root=tmp_path / "projects")

    secret_payload = {
        "answer_text": "it connects via postgres://svc_user:hunter2pass@db.internal:5432/app"
    }

    record_audit(
        agent="DiscoveryAgent",
        tool="record_answer",
        operation="write",
        workflow_state="DISCOVERY",
        inputs=secret_payload,
        entity_id="ANS-001",
        reason="answer recorded",
        result=AuditResult(success=True),
        path=project.audit_path,
        ledger_version_before=1,
        ledger_version_after=2,
    )

    raw_audit_text = project.audit_path.read_text(encoding="utf-8")
    assert "hunter2pass" not in raw_audit_text
    assert "svc_user" not in raw_audit_text
    assert "postgres://" not in raw_audit_text

    expected_hash = hash_inputs(secret_payload)
    assert expected_hash in raw_audit_text

    records = read_audit_records(project.audit_path)
    assert records[0].inputs_ref.input_hash == expected_hash
    assert records[0].inputs_ref.entity_id == "ANS-001"


def test_hash_inputs_is_deterministic_regardless_of_key_order():
    assert hash_inputs({"a": 1, "b": 2}) == hash_inputs({"b": 2, "a": 1})
    assert hash_inputs({"a": 1}) != hash_inputs({"a": 2})
