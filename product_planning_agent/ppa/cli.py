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


@app.command()
def plan(project: str) -> None:
    """Run a discovery session against a project."""
    _not_yet("plan", "T21 (outer loop) and T31 (CLI)")


@app.command()
def status(project: str) -> None:
    """Show the status board: coverage, readiness, open items, conflicts."""
    _not_yet("status", "T31 (CLI and status board)")


@app.command()
def report(project: str) -> None:
    """Write the structured report to the output folder."""
    _not_yet("report", "T31 (CLI and status board)")


def _not_yet(command: str, task: str) -> None:
    console.print(f"[yellow]`ppa {command}` is not built yet.[/yellow] It arrives with {task}.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
