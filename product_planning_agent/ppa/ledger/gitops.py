"""Git plumbing for the per-project ledger repo (DESIGN.md §2.16, §2.19.1,
S2.5, S2.7).

Every project is its own git repo, created with **no remote** — `git_init`
never configures one, and nothing in this module ever calls `git remote
add`. The ledger holds client requirements and answers verbatim; it should
not leave the machine by accident (§2.19.1).

`commit_turn` never accepts a caller-supplied message. It generates one from
the turn's own events, so every commit in a project's history is traceable
back to what actually changed — DESIGN.md §2.16's own worked example is the
shape to match: `"round 3: +2 requirements, +1 assumption, resolved
UNK-004"`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from ppa.ledger.events import Event, EventType

_TRACKED_PATHS = ("events.ndjson", "audit.ndjson", "project.json", "entities")
"""Everything under `.planning/` that `commit_turn` stages, if present. Not
`git add -A` — a turn commits exactly the ledger's own tracked state, never
whatever else happens to be sitting in the working tree."""

_CREATION_VERBS = {"created", "recorded", "opened", "asked"}
"""Which verb, for a given event type (see `_EVENT_LABELS`), means "this
entity came into existence this turn" — counted (`+N nouns`) rather than
listed individually."""

_EVENT_LABELS: dict[EventType, tuple[str, str]] = {
    EventType.REQUIREMENT_CREATED: ("requirement", "created"),
    EventType.REQUIREMENT_REVISED: ("requirement", "revised"),
    EventType.REQUIREMENT_CONFIRMED: ("requirement", "confirmed"),
    EventType.REQUIREMENT_REJECTED: ("requirement", "rejected"),
    EventType.REQUIREMENT_SUPERSEDED: ("requirement", "superseded"),
    EventType.ASSUMPTION_CREATED: ("assumption", "created"),
    EventType.ASSUMPTION_CONFIRMED: ("assumption", "confirmed"),
    EventType.ASSUMPTION_REJECTED: ("assumption", "rejected"),
    EventType.ASSUMPTION_MODIFIED: ("assumption", "modified"),
    EventType.ASSUMPTION_SUPERSEDED: ("assumption", "superseded"),
    EventType.DECISION_OPENED: ("decision", "opened"),
    EventType.DECISION_DEFERRED: ("decision", "deferred"),
    EventType.DECISION_DECIDED: ("decision", "decided"),
    EventType.DECISION_SUPERSEDED: ("decision", "superseded"),
    EventType.UNKNOWN_RECORDED: ("unknown", "recorded"),
    EventType.UNKNOWN_CLASSIFIED: ("unknown", "classified"),
    EventType.UNKNOWN_RESOLVED: ("unknown", "resolved"),
    EventType.UNKNOWN_CONVERTED: ("unknown", "converted"),
    EventType.QUESTION_ASKED: ("question", "asked"),
    EventType.QUESTION_REPLACED: ("question", "replaced"),
    EventType.ANSWER_RECORDED: ("answer", "recorded"),
    EventType.RESEARCH_RECORDED: ("research finding", "recorded"),
    EventType.RESEARCH_REPLACED: ("research finding", "replaced"),
}
"""`project.created` and the system/meta types (`txn.*`,
`coverage.recomputed`, `approval.*`, `anomaly.*`, `user.forced_ready`) are
deliberately absent — none of them are "the turn's events" a planning
narrative should mention; `project.created` gets its own commit message in
`ppa/ledger/project.py::create_project` instead."""


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def git_init(repo_dir: Path | str) -> None:
    """`git init` at `repo_dir`, plus a local commit identity so auto-commits
    work without depending on whatever (or whether) the host machine has
    configured globally. Never configures a remote — that is S2.5's entire
    point, not an oversight to fix later."""

    repo_dir = Path(repo_dir)
    _run_git(["init", "-q"], cwd=repo_dir)
    _run_git(["config", "user.name", "Product Planning Agent"], cwd=repo_dir)
    _run_git(["config", "user.email", "agent@ppa.local.invalid"], cwd=repo_dir)


def list_remotes(repo_dir: Path | str) -> list[str]:
    """Empty for a project `git_init` created and nothing has touched since —
    the assertion a freshly created project's test leans on."""

    result = _run_git(["remote"], cwd=Path(repo_dir))
    return [line for line in result.stdout.splitlines() if line.strip()]


def commit(repo_dir: Path | str, message: str, paths: list[str]) -> str | None:
    """Stage exactly `paths` (relative to `repo_dir`) and commit. Returns the
    message used, or `None` if nothing was actually staged — committing
    nothing is a no-op here, never an empty commit."""

    repo_dir = Path(repo_dir)
    _run_git(["add", "--", *paths], cwd=repo_dir)

    staged = _run_git(["diff", "--cached", "--name-only"], cwd=repo_dir)
    if not staged.stdout.strip():
        return None

    _run_git(["commit", "-q", "-m", message], cwd=repo_dir)
    return message


def _pluralize(noun: str) -> str:
    return noun if noun.endswith("s") else f"{noun}s"


def summarize_turn(events: Iterable[Event]) -> str:
    """`"+2 requirements, +1 assumption, resolved UNK-004"` (DESIGN.md
    §2.16). Creation-shaped events are counted per noun; everything else is
    listed individually by entity id, in event order."""

    creation_counts: dict[str, int] = {}
    individual: list[str] = []

    for event in events:
        label = _EVENT_LABELS.get(event.type)
        if label is None:
            continue
        noun, verb = label
        if verb in _CREATION_VERBS:
            creation_counts[noun] = creation_counts.get(noun, 0) + 1
        else:
            individual.append(f"{verb} {event.entity_id or '?'}")

    parts = [
        f"+{count} {noun if count == 1 else _pluralize(noun)}"
        for noun, count in creation_counts.items()
    ]
    parts.extend(individual)
    return ", ".join(parts) if parts else "no ledger changes"


def commit_message(events: Iterable[Event], *, round_number: int | None = None) -> str:
    summary = summarize_turn(events)
    return f"round {round_number}: {summary}" if round_number is not None else summary


def commit_turn(
    repo_dir: Path | str,
    events: Iterable[Event],
    *,
    round_number: int | None = None,
) -> str | None:
    """Stage whatever exists under `.planning/` (`_TRACKED_PATHS`) and commit
    with a message generated from `events`. Returns the message used, or
    `None` if there was nothing to stage."""

    repo_dir = Path(repo_dir)
    planning_dir = repo_dir / ".planning"
    existing = [
        str((planning_dir / name).relative_to(repo_dir))
        for name in _TRACKED_PATHS
        if (planning_dir / name).exists()
    ]
    if not existing:
        return None

    return commit(repo_dir, commit_message(events, round_number=round_number), paths=existing)
