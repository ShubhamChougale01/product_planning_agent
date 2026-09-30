"""The eval harness (T33, `tasks/t33_eval_fixtures_and_personas.md`).

Drives one real, multi-round Discovery session for a `(fixture, persona)`
pair: invoke the agent, find whatever `QuestionAnswer` entities the turn
left `PENDING`, hand each to the persona, record its answer
(`ppa.tools.interaction.answer_pending_question`), and invoke again — until
no questions remain, an escalation/failure occurs, or `max_rounds` is
reached. Every real turn (`ppa.agents.discovery.DiscoveryAgent().invoke`)
makes a live model call — see `tests/eval/test_matrix.py`, marked
`live_model` throughout, never in the default suite.

**A full fixture x persona run can be launched with one command**, per this
task's own Done-when box:

    python -m tests.eval.harness                       # every fixture x every persona
    python -m tests.eval.harness --fixture f01_vague_internal_ops_tool --persona vague
    python -m tests.eval.harness --persona always_idk --max-rounds 4
"""

from __future__ import annotations

import argparse
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from ppa.agents.base import AgentResultStatus
from ppa.agents.discovery import DiscoveryAgent
from ppa.config.profiles import UserProfile
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import create_project
from ppa.ledger.store import read_project_meta
from ppa.tools.dispatch import InvocationContext
from ppa.tools.interaction import answer_pending_question

from .personas import PERSONAS, Persona

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEFAULT_MAX_ROUNDS = 6


@dataclass(frozen=True)
class Fixture:
    """One seed requirement + profile + the axes it was designed to cover
    (`tests/eval/fixtures/*.yaml`, loaded verbatim — this class never
    invents a default any fixture doesn't state)."""

    name: str
    seed_requirement: str
    profile: UserProfile
    axes: dict[str, str]
    notes: str = ""
    adversarial: bool = False

    @classmethod
    def load(cls, path: Path) -> "Fixture":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            name=data["name"],
            seed_requirement=data["seed_requirement"].strip(),
            profile=UserProfile(**data["profile"]),
            axes=dict(data.get("axes") or {}),
            notes=(data.get("notes") or "").strip(),
            adversarial=bool(data.get("adversarial", False)),
        )


def load_fixtures() -> list[Fixture]:
    """Every `*.yaml` in `tests/eval/fixtures/`, sorted by filename — always
    the same ten, in the same order, on every call."""

    return [Fixture.load(p) for p in sorted(FIXTURES_DIR.glob("*.yaml"))]


def load_fixture(name: str) -> Fixture:
    for fixture in load_fixtures():
        if fixture.name == name:
            return fixture
    raise KeyError(f"no fixture named {name!r} under {FIXTURES_DIR}")


@dataclass
class RoundLog:
    round_number: int
    agent_status: str
    agent_summary: str
    questions_answered: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionReport:
    """What one `run_session` call produced — enough to answer both this
    task's own questions: did the persona complete the session unattended,
    and did the fixture break the agent."""

    fixture: str
    persona: str
    rounds: list[RoundLog] = field(default_factory=list)
    broke: bool = False
    break_reason: str | None = None
    stopped_reason: str = "unknown"
    final_mode: str | None = None
    ready: bool = False
    project: Any = None
    """The real `Project` handle this session ran against, once created —
    `None` only if project creation itself failed (`report.broke` in that
    case). Lets a caller inspect final entities directly (`ppa.ledger.
    materialize.current_entities(report.project.events_path)`) without
    `run_session` having to know in advance what every caller might want
    to check for."""

    @property
    def completed(self) -> bool:
        """"Completed unattended" means exactly "never broke" — the session
        may perfectly legitimately stop at the round cap without reaching
        READY (v1 sessions routinely run far more than a handful of real
        rounds); what matters is that nothing required a human and nothing
        crashed."""

        return not self.broke


def _ctx(project) -> InvocationContext:
    return InvocationContext(
        agent_id="discovery",
        workflow_state="DISCOVERY",
        session_id=f"eval-{uuid.uuid4().hex[:8]}",
        audit_path=project.audit_path,
    )


def _pending_questions(project) -> list[Any]:
    entities = current_entities(project.events_path)
    return sorted(
        (
            entity
            for entity_id, entity in entities.items()
            if entity_type_for(entity_id) is EntityType.QUESTION_ANSWER and entity.status == "PENDING"
        ),
        key=lambda q: q.id,
    )


def run_session(
    fixture: Fixture,
    persona_factory: Callable[[], Persona],
    *,
    projects_root: Path,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> SessionReport:
    """One real session: `persona_factory()` for a fresh instance (never
    shared across sessions — see `personas.py`'s own docstring), a fresh
    project from `fixture`, then invoke/answer/invoke until the loop's own
    stopping conditions. Never raises — every failure this function can
    observe (a raised exception, an unrecoverable `AgentResult`, a rejected
    answer write) becomes `report.broke = True` with a stated reason
    instead, so a caller driving the full matrix never has one bad
    combination kill the run."""

    persona = persona_factory()
    report = SessionReport(fixture=fixture.name, persona=persona.name)

    try:
        project = create_project(
            f"{fixture.name}-{persona.name}-{uuid.uuid4().hex[:6]}",
            fixture.seed_requirement,
            fixture.profile,
            projects_root=projects_root,
        )
    except Exception as exc:  # the fixture itself broke project creation
        report.broke = True
        report.break_reason = f"project creation failed: {exc!r}"
        report.stopped_reason = "broke"
        return report

    report.project = project
    round_number = 0
    for round_number in range(1, max_rounds + 1):
        ctx = _ctx(project)
        try:
            result = DiscoveryAgent().invoke(ctx)
        except Exception as exc:
            report.broke = True
            report.break_reason = f"round {round_number}: agent invocation raised {exc!r}"
            report.stopped_reason = "broke"
            return report

        round_log = RoundLog(round_number=round_number, agent_status=result.status.value, agent_summary=result.summary)
        report.rounds.append(round_log)

        if result.status in (AgentResultStatus.NON_RECOVERABLE, AgentResultStatus.RECOVERABLE):
            report.broke = True
            report.break_reason = f"round {round_number}: agent reported {result.status.value}: {result.summary}"
            report.stopped_reason = "broke"
            return report

        pending = _pending_questions(project)
        if not pending:
            report.stopped_reason = "no_more_questions"
            break

        for question in pending:
            answer = persona.answer(question.model_dump(mode="json"), round_number=round_number)
            answer_result = answer_pending_question(
                project, question.id, answer,
                actor_id=f"persona:{persona.name}", session_id=ctx.session_id, workflow_state="DISCOVERY",
            )
            if not answer_result.success:
                report.broke = True
                report.break_reason = (
                    f"round {round_number}: recording the persona's answer to {question.id} failed: "
                    f"{answer_result.error}"
                )
                report.stopped_reason = "broke"
                return report
            round_log.questions_answered.append({"question_id": question.id, "answer": answer})
    else:
        report.stopped_reason = "round_cap_reached"

    entities = current_entities(project.events_path)
    meta = read_project_meta(project.events_path)
    report.final_mode = meta.get("discovery_mode")
    ready, _blockers = check_readiness(entities, fixture.profile)
    report.ready = ready
    return report


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one or more real fixture x persona Discovery sessions (live model calls).",
    )
    parser.add_argument("--fixture", action="append", help="Fixture name(s) to run; default: all ten.")
    parser.add_argument("--persona", action="append", help="Persona name(s) to run; default: all six.")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    args = parser.parse_args(argv)

    fixtures = [load_fixture(name) for name in args.fixture] if args.fixture else load_fixtures()
    persona_names = args.persona or list(PERSONAS)

    broke_count = 0
    with tempfile.TemporaryDirectory() as tmp:
        projects_root = Path(tmp) / "projects"
        for fixture in fixtures:
            for persona_name in persona_names:
                report = run_session(
                    fixture, PERSONAS[persona_name], projects_root=projects_root, max_rounds=args.max_rounds,
                )
                status = "BROKE" if report.broke else "ok"
                broke_count += int(report.broke)
                print(
                    f"[{status}] {fixture.name} x {persona_name}: {report.stopped_reason}, "
                    f"{len(report.rounds)} round(s), mode={report.final_mode}, ready={report.ready}"
                )
                if report.broke:
                    print(f"    reason: {report.break_reason}")

    print(f"\n{broke_count} broke out of {len(fixtures) * len(persona_names)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
