"""Command line surface for the Product Planning Agent.

Only ``doctor`` does real work at T01. The rest of the commands arrive with T31;
they are declared here so the shape of the tool is visible from day one and so
``--help`` is a meaningful check that the package imports cleanly.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="ppa",
    help="Turn a rough requirement into a versioned, auditable planning ledger.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@app.command()
def doctor() -> None:
    """Check that the environment and the model seam are wired up correctly."""
    from ppa.providers.model import ModelProvider

    provider = ModelProvider.from_config(CONFIG_DIR / "model.yaml")

    table = Table(title="ppa doctor", show_header=False, title_justify="left")
    for key, value in provider.describe().items():
        table.add_row(key.replace("_", " "), str(value))
    console.print(table)

    if provider.cfg.auth_source == "subscription":
        console.print(
            "\n[dim]Running on your Claude Code login — no API key involved. "
            "Verified 2026-09-23, see docs/decisions/auth.md.[/dim]"
        )


@app.command()
def new(
    name: str,
    seed_requirement: str = typer.Option(
        ..., "--seed-requirement", "--seed", help="A rough one-line requirement to start from."
    ),
    role: str = typer.Option("engineer", help="engineer | product | mixed"),
    technical_depth: str = typer.Option("medium", help="high | medium | low"),
    domain_familiarity: str = typer.Option("medium", help="high | medium | low"),
) -> None:
    """Start a new planning project."""
    from ppa.config.profiles import UserProfile
    from ppa.ledger.project import VERBATIM_STORAGE_NOTICE, create_project

    profile = UserProfile(
        role=role, technical_depth=technical_depth, domain_familiarity=domain_familiarity
    )
    project = create_project(name, seed_requirement, profile)

    console.print(f"[green]Created[/green] project [bold]{project.slug}[/bold] at {project.path}")
    console.print(f"\n[yellow]{VERBATIM_STORAGE_NOTICE}[/yellow]")


def _next_session_id(project) -> str:
    """`"session-{n}"`, one past however many distinct `session_id`s have
    already appeared in `events.ndjson` — a plain fold over the event log,
    the same "no separate counter needs to exist anywhere" principle
    `ppa.orchestrator.context.rounds_from_events` already applies to
    rounds."""

    from ppa.orchestrator.context import read_events

    seen: list[str] = []
    for event in read_events(project.events_path):
        if event.session_id not in seen:
            seen.append(event.session_id)
    return f"session-{len(seen) + 1}"


@app.command()
def chat(project: str) -> None:
    """The main loop: run outer-loop turns, rendering and collecting
    answers for every question a turn leaves `PENDING`, until the session
    suspends for a reason that isn't a question, completes, or escalates."""

    from ppa.ledger.materialize import current_entities, entity_type_for
    from ppa.ledger.models import EntityType
    from ppa.ledger.project import open_project
    from ppa.orchestrator import loop as orchestrator_loop
    from ppa.render.question_card import parse_answer, render_question_card
    from ppa.render.status_board import render_status_board
    from ppa.tools.interaction import answer_pending_question

    proj = open_project(project)
    session_id = _next_session_id(proj)

    while True:
        step = orchestrator_loop.run_turn(proj, proj.profile, session_id=session_id)
        proj = proj.model_copy(update={"workflow_state": step.workflow_state})
        console.print(f"[dim]{step.summary}[/dim]")

        if step.outcome is orchestrator_loop.StepOutcome.SUSPENDED:
            entities = current_entities(proj.events_path)
            pending = sorted(
                (
                    e for eid, e in entities.items()
                    if entity_type_for(eid) is EntityType.QUESTION_ANSWER and e.status == "PENDING"
                ),
                key=lambda q: q.id,
            )
            for question in pending:
                console.print("")
                console.print(render_question_card(question.model_dump(mode="json")))
                raw = typer.prompt(">")
                answer = parse_answer(raw)
                answer_pending_question(
                    proj, question.id, answer,
                    actor_id="user:local", session_id=session_id, workflow_state=proj.workflow_state,
                )
            continue

        if step.outcome in (
            orchestrator_loop.StepOutcome.COMPLETE,
            orchestrator_loop.StepOutcome.ESCALATED,
            orchestrator_loop.StepOutcome.NOT_IMPLEMENTED,
        ):
            console.print("")
            console.print(render_status_board(proj, current_entities(proj.events_path)))
            break


@app.command()
def status(
    project: str,
    items: bool = typer.Option(False, "--items", help="Show just the readiness/open-items list."),
    cost: bool = typer.Option(False, "--cost", help="Show the token/cost breakdown per agent and per mode."),
) -> None:
    """Show the status board: coverage, readiness, open items — one surface."""

    from ppa.ledger.materialize import current_entities
    from ppa.ledger.project import open_project
    from ppa.render.status_board import render_cost_report, render_open_items, render_status_board

    proj = open_project(project)
    if cost:
        console.print(render_cost_report(proj))
        return
    entities = current_entities(proj.events_path)
    if items:
        console.print(render_open_items(proj, entities))
    else:
        console.print(render_status_board(proj, entities))


@app.command()
def history(project: str, entity_id: str) -> None:
    """Version trail: every recorded change to one entity, oldest first."""

    from ppa.ledger.materialize import current_entities
    from ppa.ledger.project import open_project
    from ppa.render.status_board import render_history

    proj = open_project(project)
    entities = current_entities(proj.events_path)
    console.print(render_history(entity_id, entities))


@app.command(name="force-ready")
def force_ready(
    project: str,
    reason: str = typer.Option(..., "--reason", help="Why the gate is being overridden — recorded on the event."),
) -> None:
    """Override the readiness gate. Records every blocker that was skipped."""

    from ppa.engines.readiness import force_ready as run_force_ready
    from ppa.ledger.materialize import current_entities
    from ppa.ledger.project import open_project
    from ppa.render.status_board import gate_inputs

    proj = open_project(project)
    entities = current_entities(proj.events_path)
    review_approved, confirmed_areas, unresolved_conflicts = gate_inputs(proj)
    run_force_ready(
        entities, proj.profile, reason, proj.events_path,
        actor_id="user:local", session_id=_next_session_id(proj), workflow_state=proj.workflow_state,
        confirmed_areas=confirmed_areas, unresolved_conflicts=unresolved_conflicts, review_approved=review_approved,
    )
    console.print(f"[yellow]Readiness gate overridden.[/yellow] {reason}")


@app.command()
def report(project: str) -> None:
    """Write the structured report to the output folder."""
    _not_yet("report", "T31 (CLI and status board)")


@app.command()
def why(project: str, decision_id: str) -> None:
    """Explain why a decision was made, from the ledger alone."""
    from ppa.ledger.materialize import current_entities
    from ppa.ledger.project import open_project
    from ppa.render.guidance_card import render_why
    from ppa.render.status_board import render_provenance

    proj = open_project(project)
    entities = current_entities(proj.events_path)
    console.print(render_why(decision_id, entities))
    console.print(render_provenance(decision_id, proj.audit_path))


@app.command(name="client-questions")
def client_questions(project: str) -> None:
    """Render every open item owned externally as a sendable client questionnaire."""
    from ppa.config.house_style import load_house_style
    from ppa.ledger.materialize import current_entities
    from ppa.ledger.project import open_project
    from ppa.render.client_questions import render_client_questionnaire

    proj = open_project(project)
    entities = current_entities(proj.events_path)
    style = load_house_style()
    console.print(render_client_questionnaire(entities, style))


def _not_yet(command: str, task: str) -> None:
    console.print(f"[yellow]`ppa {command}` is not built yet.[/yellow] It arrives with {task}.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
