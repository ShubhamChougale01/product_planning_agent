"""Case 16 (S12.2) — secret pasted into an answer: redacted pre-append;
absent from events, audit **and** git.

Proven directly against the real redaction seam (`ppa.ledger.secrets.
scan_and_redact`, wired into `ppa.tools.interaction.answer_pending_question`
before any event is constructed) and the real per-project git repo
(`ppa.ledger.project.create_project` calls `git_init`; `ppa.ledger.gitops.
commit_turn` is the real function a turn uses to commit `.planning/` state).
No model call: this proves the redaction-before-write contract holds for a
raw secret string, not that a model would never echo one back — a
`git log -p --all` scan (not just a file read) closes the "and git" half of
the case literally, since redacted-before-write does not by itself prove a
raw value never touched an earlier, unredacted git blob.
"""

from __future__ import annotations

import subprocess

from ppa.ledger.gitops import commit_turn
from ppa.ledger.materialize import current_entities
from ppa.orchestrator.context import read_events
from ppa.tools.interaction import ask_user, answer_pending_question
from tests.eval.cases._helpers import make_project, writer_kwargs
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_16"
CASE_NAME = "secret pasted into an answer, redacted everywhere"

_FAKE_KEY_PREFIX = "sk-"
_FAKE_KEY_BODY = "FAKE0PIC1234567890abcdefghijklmnop"
_SECRET = _FAKE_KEY_PREFIX + _FAKE_KEY_BODY
"""Built by concatenation, not a single quoted literal — matches `ppa.
ledger.secrets._SK_PREFIXED` at runtime (what this case needs) without
itself looking like a committed credential to `tests/test_secrets/
test_repo_hygiene.py::test_no_credential_values_are_committed`, which flags
a `name = "16+ char value"` literal on sight, not just a real key."""


def _git_history_text(repo_dir) -> str:
    result = subprocess.run(
        ["git", "log", "--all", "-p"], cwd=str(repo_dir), check=True, capture_output=True, text=True,
    )
    return result.stdout


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path)
    notes: list[str] = []
    passed = True

    asked = ask_user(
        [{"text": "What credential should the integration use?", "why_asked": "scoping the integration"}],
        project, **writer_kwargs(),
    )
    question_id = asked.data[0]["question_id"]

    answered = answer_pending_question(
        project, question_id,
        {"answer_kind": "answered", "answer_text": f"Use this one: {_SECRET}"},
        **writer_kwargs(),
    )
    if not answered.success:
        passed = False
        notes.append(f"answer_pending_question failed: {answered.error}")

    entities = current_entities(project.events_path)
    ans = entities[answered.data["entity_id"]]
    if _SECRET in (ans.answer_text or ""):
        passed = False
        notes.append("the raw secret is present on the materialized ANS entity")
    if "[REDACTED:credential]" not in (ans.answer_text or ""):
        passed = False
        notes.append("no redaction marker found on the materialized ANS entity")

    events_raw = project.events_path.read_text(encoding="utf-8")
    if _SECRET in events_raw:
        passed = False
        notes.append("the raw secret is present in events.ndjson")

    if project.audit_path.exists():
        audit_raw = project.audit_path.read_text(encoding="utf-8")
        if _SECRET in audit_raw:
            passed = False
            notes.append("the raw secret is present in audit.ndjson")

    events = read_events(project.events_path)
    commit_turn(project.path, events, round_number=1)

    history = _git_history_text(project.path)
    secrets_leaked = 1 if _SECRET in history else 0
    if secrets_leaked:
        passed = False
        notes.append("the raw secret appears somewhere in git history (git log --all -p)")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        secrets_leaked=secrets_leaked,
        tool_calls_attempted=2,
    )


def test_secret_pasted_into_an_answer_is_absent_everywhere(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
