"""ask_user — the interaction contract (T17, DESIGN.md §1.4, §3.2, S5.6).

Every question the user ever sees goes through here, which makes this the
right place to enforce the batch cap and to guarantee that "I don't know"
is always a first-class option rather than a failure. **At most 5 questions
per call; 3 is the target** — a 6-question batch is rejected as VALIDATION
before a single event is written.

Each question dict carries `text`, a required `why_asked` (the one-line
reason this turns a questionnaire into a partner), optional `target_areas`,
optional `suggested_options` and an optional `recommended_default`. A
question may optionally carry an embedded `answer` dict — `ask_user` does
not itself collect input from a terminal (that surface is T31's job); it
persists whatever answer the caller already obtained, exactly the way
`ppa.tools.discovery_tools`'s `manage_*` writers don't care whether a
`statement` came from a model or a person, only that one was supplied.

**Two id series, one conceptual record.** `QuestionAnswer.__doc__` (T02)
already states the rule: `Q-nnn` while awaiting an answer, `ANS-nnn` once
one is recorded. This module implements that literally as three events per
answered question, atomic in effect though not wrapped in a transaction
marker (no multi-step rollback need exists yet — each event is independently
valid, matching §2.14's "a rejected write leaves nothing to roll back"):

1. `QUESTION_ASKED` creates `Q-nnn`, `status=PENDING`.
2. `QUESTION_REPLACED` moves that same `Q-nnn` to `status=REPLACED` — it has
   been superseded by a real answer record, the same way a superseded
   Requirement is never mutated in place.
3. `ANSWER_RECORDED` creates a *new* `ANS-nnn`, `status=ANSWERED`, carrying
   every field the question had plus the answer itself.

A question asked with no embedded answer stops after step 1 — still a
legitimate `Q-nnn`, `PENDING`, exactly what a real interactive CLI (T31)
would create before it has collected a response.

`decide_later` intentionally does **not** open a `DEC-nnn` Decision from
inside this module — DESIGN.md's own routing table (§3.4, built by T26) is
what decides how an answer becomes a Decision, an Assumption or a research
question; `manage_decision` already exists for that and this tool does not
duplicate it. `dont_know`'s `dont_know_kind` classification is T26's job
too — this module only records the raw affordance and passes through
whatever classification the caller already has, if any.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ppa.ledger.audit import AuditResult, record_audit
from ppa.ledger.events import EventType
from ppa.ledger.materialize import rebuild_all
from ppa.ledger.models import HistoryEntry
from ppa.ledger.project import DEFAULT_PROJECTS_ROOT, Project, open_project
from ppa.ledger.secrets import scan_and_redact
from ppa.ledger.store import append_event_with_id, ledger_version
from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult
from ppa.tools.registry import register
from ppa.tools.spec import ToolSpec
from ppa.validation import infer_validation_layer

_MAX_QUESTIONS = 5
_ANSWER_KINDS = {"answered", "dont_know", "decide_later", "not_relevant"}


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def _error(category: ErrorCategory, code: str, description: str, context: dict[str, Any] | None = None) -> ToolResult:
    rule = CATEGORY_RULES[category]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=category,
            code=code,
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=description,
            context=context or {},
        ),
    )


def _validate_batch(questions: list[dict[str, Any]]) -> ToolResult | None:
    if not questions:
        return _error(ErrorCategory.VALIDATION, "EMPTY_BATCH", "ask_user requires at least one question")
    if len(questions) > _MAX_QUESTIONS:
        return _error(
            ErrorCategory.VALIDATION, "BATCH_TOO_LARGE",
            f"ask_user: at most {_MAX_QUESTIONS} questions per call (3 is the target). Received: {len(questions)}.",
        )

    for idx, q in enumerate(questions):
        if not (q.get("text") or "").strip():
            return _error(ErrorCategory.VALIDATION, "MISSING_TEXT", f"ask_user: question[{idx}] requires text")
        if not (q.get("why_asked") or "").strip():
            return _error(
                ErrorCategory.VALIDATION, "MISSING_WHY_ASKED",
                f"ask_user: question[{idx}] ({q.get('text', '')!r}) requires why_asked — "
                "every question must explain itself, or it is a questionnaire, not a partner",
            )

        answer = q.get("answer")
        if answer is None:
            continue
        kind = answer.get("answer_kind")
        if kind not in _ANSWER_KINDS:
            return _error(
                ErrorCategory.VALIDATION, "INVALID_ANSWER_KIND",
                f"ask_user: question[{idx}] answer_kind must be one of {sorted(_ANSWER_KINDS)}, got {kind!r}",
            )
        if kind in ("answered", "not_relevant") and not (answer.get("answer_text") or "").strip():
            meaning = "the answer text" if kind == "answered" else "a reason it isn't relevant"
            return _error(
                ErrorCategory.VALIDATION, "MISSING_ANSWER_TEXT",
                f"ask_user: question[{idx}] answer_kind={kind!r} requires answer_text ({meaning}) — "
                "not_relevant must record why, never silently drop the question",
            )

    return None


def _commit_one(
    project: Project,
    *,
    tool: str,
    agent_id: str,
    workflow_state: str,
    fields: dict[str, Any],
    args: dict[str, Any],
    reason: str,
    id_prefix: str | None = None,
    idem_key: str | None = None,
) -> ToolResult:
    version_before = ledger_version(project.events_path)
    write_result = append_event_with_id(fields, project.events_path, id_prefix=id_prefix, idem_key=idem_key)
    version_after = ledger_version(project.events_path)
    result = ToolResult(
        success=True,
        result_count=1,
        data={"entity_id": write_result.entity_id, "event_id": write_result.event_id, "replayed": write_result.replayed},
    )
    record_audit(
        agent=agent_id, tool=tool, operation="write", workflow_state=workflow_state, inputs=args, reason=reason,
        result=AuditResult(success=True), path=project.audit_path, entity_id=write_result.entity_id,
        ledger_version_before=version_before, ledger_version_after=version_after,
    )
    return result


def _ask_and_maybe_answer_one(
    project: Project,
    q: dict[str, Any],
    idx: int,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str,
    agent_id: str,
    actor_role: str,
    now: datetime,
    round_number: int,
    idem_key: str | None,
) -> dict[str, Any]:
    text, _findings = scan_and_redact(q["text"])
    why_asked, _findings = scan_and_redact(q["why_asked"])
    target_areas = list(q.get("target_areas") or [])
    suggested_options = list(q.get("suggested_options") or [])
    recommended_default = q.get("recommended_default")
    agent_name = None if actor_role == "user" else agent_id

    question_after = dict(
        id="PENDING", version=1, created_at=now.isoformat(), updated_at=now.isoformat(),
        created_by=actor_id, updated_by=actor_id, history=[],
        status="PENDING", text=text, why_asked=why_asked, target_areas=target_areas,
        round=round_number, suggested_options=suggested_options, recommended_default=recommended_default,
        answer_kind=None, dont_know_kind=None, answer_text=None, answered_at=None,
    )
    ask_fields = dict(
        ts=now, type=EventType.QUESTION_ASKED, entity_id=None, actor_id=actor_id, actor_role=actor_role,
        agent_name=agent_name, workflow_state=workflow_state, txn_id=None, source="ask_user",
        reason=f"asked: {text[:120]}", before=None, after=question_after, session_id=session_id,
    )
    ask_result = _commit_one(
        project, tool="ask_user", agent_id=agent_id, workflow_state=workflow_state, fields=ask_fields, args=q,
        reason="question asked", id_prefix="Q", idem_key=f"{idem_key}:ask:{idx}" if idem_key else None,
    )
    question_id = ask_result.data["entity_id"]

    entry: dict[str, Any] = {
        "question_id": question_id, "answer_id": None, "answer_kind": None, "replayed": ask_result.data["replayed"],
    }

    answer = q.get("answer")
    if answer is None:
        return entry

    kind = answer["answer_kind"]
    answer_text = answer.get("answer_text")
    if answer_text:
        answer_text, _findings = scan_and_redact(answer_text)
    dont_know_kind = answer.get("dont_know_kind")

    question_snapshot = dict(question_after, id=question_id)
    replaced_after = dict(
        question_snapshot, status="REPLACED", version=2, updated_at=now.isoformat(), updated_by=actor_id,
        history=[
            HistoryEntry(
                field="status", old_value="PENDING", new_value="REPLACED",
                changed_at=now, changed_by=actor_id, reason="superseded by a recorded answer",
            ).model_dump(mode="json")
        ],
    )
    replace_fields = dict(
        ts=now, type=EventType.QUESTION_REPLACED, entity_id=question_id, actor_id=actor_id, actor_role=actor_role,
        agent_name=agent_name, workflow_state=workflow_state, txn_id=None, source="ask_user",
        reason="answer recorded, superseding the pending question", before=question_snapshot,
        after=replaced_after, session_id=session_id,
    )
    _commit_one(
        project, tool="ask_user", agent_id=agent_id, workflow_state=workflow_state, fields=replace_fields, args=q,
        reason="question replaced by answer", idem_key=f"{idem_key}:replace:{idx}" if idem_key else None,
    )

    answer_after = dict(
        id="PENDING", version=1, created_at=now.isoformat(), updated_at=now.isoformat(),
        created_by=actor_id, updated_by=actor_id, history=[],
        status="ANSWERED", text=text, why_asked=why_asked, target_areas=target_areas,
        round=round_number, suggested_options=suggested_options, recommended_default=recommended_default,
        answer_kind=kind, dont_know_kind=dont_know_kind, answer_text=answer_text, answered_at=now.isoformat(),
    )
    answer_fields = dict(
        ts=now, type=EventType.ANSWER_RECORDED, entity_id=None, actor_id=actor_id, actor_role=actor_role,
        agent_name=agent_name, workflow_state=workflow_state, txn_id=None, source="ask_user",
        reason=f"answer recorded ({kind})", before=None, after=answer_after, session_id=session_id,
    )
    answer_result = _commit_one(
        project, tool="ask_user", agent_id=agent_id, workflow_state=workflow_state, fields=answer_fields, args=q,
        reason="answer recorded", id_prefix="ANS", idem_key=f"{idem_key}:answer:{idx}" if idem_key else None,
    )

    entry["answer_id"] = answer_result.data["entity_id"]
    entry["answer_kind"] = kind
    return entry


def ask_user(
    questions: list[dict[str, Any]],
    project: Project,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    agent_id: str = "discovery",
    actor_role: str = "agent",
    round_number: int = 1,
    now: datetime | None = None,
    idem_key: str | None = None,
) -> ToolResult:
    """Persist ≤5 questions (each optionally carrying an already-obtained
    answer) as `Q-nnn`/`ANS-nnn` entities. See the module docstring for the
    three-event answered-question sequence and the batch-cap rule."""

    ts = _now(now)

    invalid = _validate_batch(questions)
    if invalid is not None:
        version = ledger_version(project.events_path)
        record_audit(
            agent=agent_id, tool="ask_user", operation="reject", workflow_state=workflow_state,
            inputs={"questions": questions}, reason="batch validation failed",
            result=AuditResult(success=False, category=invalid.error.category, code=invalid.error.code),
            path=project.audit_path, validation_layer_failed=infer_validation_layer(invalid.error),
            ledger_version_before=version, ledger_version_after=version,
        )
        return invalid

    entries = [
        _ask_and_maybe_answer_one(
            project, q, idx, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state,
            agent_id=agent_id, actor_role=actor_role, now=ts, round_number=round_number, idem_key=idem_key,
        )
        for idx, q in enumerate(questions)
    ]
    rebuild_all(project.events_path)
    return ToolResult(success=True, result_count=len(entries), data=entries)


async def _ask_user_handler(args: dict[str, Any]) -> dict[str, Any]:
    project_slug = args.get("project_slug")
    questions = args.get("questions") or []
    if not project_slug:
        result = _error(ErrorCategory.VALIDATION, "MISSING_PROJECT_SLUG", "ask_user: requires project_slug")
    else:
        projects_root = args.get("projects_root", DEFAULT_PROJECTS_ROOT)
        project = open_project(project_slug, projects_root=projects_root)
        result = ask_user(
            questions,
            project,
            actor_id=args.get("actor_id", "agent:discovery"),
            session_id=args.get("session_id", "session-unknown"),
            workflow_state=args.get("workflow_state", "DISCOVERY"),
            agent_id=args.get("agent_id", "discovery"),
            actor_role=args.get("actor_role", "agent"),
            round_number=args.get("round_number", 1),
            idem_key=args.get("idem_key"),
        )
    return {"content": [{"type": "text", "text": result.model_dump_json()}], "is_error": not result.success}


ASK_USER_SPEC = ToolSpec(
    name="ask_user",
    purpose="Ask the user up to 5 questions in one batch, each with why/options/default, and record whichever of the four affordances they choose.",
    inputs={
        "questions": "list[dict], 1-5 questions — see edge_cases for the shape of each",
        "project_slug": "str, the project's slug",
        "round_number": "int, the discovery round this batch belongs to — defaults to 1",
    },
    required=["questions", "project_slug"],
    optional=["round_number"],
    formats={
        "questions": "list of at most 5 dicts, each {text, why_asked, target_areas?, suggested_options?, recommended_default?, answer?}",
    },
    returns="ToolResult with data=[{question_id, answer_id, answer_kind, replayed}, ...], one entry per question.",
    examples=[
        'ask_user(questions=[{"text": "Which payment processor?", "why_asked": "determines integration scope", "suggested_options": ["Stripe", "Braintree"], "answer": {"answer_kind": "answered", "answer_text": "Stripe"}}], project_slug="invoice-tracker")',
        'ask_user(questions=[{"text": "Who approves refunds?", "why_asked": "affects the approval workflow", "answer": {"answer_kind": "dont_know"}}], project_slug="invoice-tracker")',
    ],
    edge_cases=[
        "a 6th question in the same call rejects the whole batch as VALIDATION — nothing is written",
        "a question missing why_asked rejects the whole batch as VALIDATION",
        "answer_kind=not_relevant without answer_text (the reason) is rejected — never silently dropped",
        "a question asked with no embedded answer is persisted as Q-nnn PENDING only, for a caller (T31's CLI) to answer later",
    ],
    limitations=[
        "does not itself prompt a terminal for input — the caller supplies any answer already obtained",
        "decide_later does not open a Decision — that routing belongs to manage_decision, called separately",
    ],
    use_when=[
        "the agent has identified real gaps and needs the user's own input to proceed",
        "an answer has already been obtained (from any surface) and needs to be recorded on the ledger",
    ],
    do_not_use_when=[
        "the agent could resolve this itself with a documented assumption — use manage_assumption instead",
        "more than 5 questions are ready — split into multiple rounds, never one oversized batch",
    ],
    related_tools={
        "manage_decision": "opens a real Decision from a decide_later or dont_know answer; ask_user never does",
        "read_planning_state": "reads recorded Q&A via scope=entity/history; ask_user never reads, only writes",
    },
)

register(ASK_USER_SPEC, _ask_user_handler, owner_agents=["discovery"])
