"""Project lifecycle: create, open, list (DESIGN.md §2.19.1, S2.5, S2.7).

Two deliberate choices, straight from the design: **new projects have no git
remote** (`ppa/ledger/gitops.py::git_init` never configures one), and the
verbatim-storage notice below is shown, not buried — most of the risk in
§2.19.1 is solved by the user knowing the ledger holds their answers
verbatim before they start typing into it.

`project.json` (a sibling of `events.ndjson`) is shared with T07's own
`id_counters`/`idempotency` map — this module owns the rest of its shape:
`name`, `slug`, `profile`, `workflow_state`, `created_at`. All reads/writes
go through `ppa/ledger/store.py`'s public wrappers, under the same per-path
lock T07 already uses for that file, so the two halves never race.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ppa.config.profiles import UserProfile
from ppa.ledger.events import EventType
from ppa.ledger.gitops import commit, git_init
from ppa.ledger.secrets import scan_and_redact
from ppa.ledger.store import append_event, path_lock, read_project_meta, write_project_meta

DEFAULT_PROJECTS_ROOT = Path("projects")

VERBATIM_STORAGE_NOTICE = (
    "the ledger stores your requirements and answers verbatim, including client "
    "information; it is a local git repo; add a remote only if that is appropriate "
    "for this project"
)

_GITIGNORE_TEMPLATE = (
    "# Product Planning Agent — never tracked in this project's own history.\n"
    "*.local.*\n"
    "scratch/\n"
)

_SLUG_INVALID = re.compile(r"[^a-z0-9]+")

_PROJECT_META_FIELDS = ("name", "profile", "workflow_state", "created_at")


class Project(BaseModel):
    """The in-memory handle `create_project`/`open_project` return. `path` is
    the project's own root directory — the git repo boundary — with
    `.planning/` (events, audit, `project.json`, `entities/`) beneath it."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    profile: UserProfile
    workflow_state: str
    created_at: datetime
    path: Path

    @property
    def planning_dir(self) -> Path:
        return self.path / ".planning"

    @property
    def events_path(self) -> Path:
        return self.planning_dir / "events.ndjson"

    @property
    def audit_path(self) -> Path:
        return self.planning_dir / "audit.ndjson"


def _slugify(name: str) -> str:
    slug = _SLUG_INVALID.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"project name {name!r} has no usable characters for a slug")
    return slug


def create_project(
    name: str,
    seed_requirement: str,
    profile: UserProfile,
    *,
    projects_root: Path | str = DEFAULT_PROJECTS_ROOT,
    actor_id: str = "user:local",
    session_id: str = "session-init",
) -> Project:
    """`<projects_root>/<slug>/`: its own independent git repo with **no
    remote configured**, a `.gitignore` excluding `*.local.*` and `scratch/`,
    and a `project.created` event. Two commits result — the scaffold, then
    the ledger's first event — so `git log --oneline` reads as a narrative
    from the very first line.

    `seed_requirement` is free text a user typed in, so it is scanned and
    redacted exactly like `append_event` already treats `source`/`reason`
    (§2.19.1: redact before the write, because an NDJSON line can never be
    unwritten). It travels in `project.created`'s `after` payload for T24
    (Intake mode) to turn into real `Requirement` entities later —
    `project.json` holds only project-level fields, never ledger content.
    """

    slug = _slugify(name)
    project_dir = Path(projects_root) / slug
    if project_dir.exists():
        raise FileExistsError(f"a project already exists at {project_dir}")

    planning_dir = project_dir / ".planning"
    planning_dir.mkdir(parents=True)

    git_init(project_dir)
    (project_dir / ".gitignore").write_text(_GITIGNORE_TEMPLATE, encoding="utf-8")
    commit(project_dir, "scaffold: .gitignore", paths=[".gitignore"])

    events_path = planning_dir / "events.ndjson"
    redacted_seed, _findings = scan_and_redact(seed_requirement)
    created_at = datetime.now(timezone.utc)

    append_event(
        dict(
            ts=created_at,
            type=EventType.PROJECT_CREATED,
            entity_id=None,
            actor_id=actor_id,
            actor_role="user",
            agent_name=None,
            workflow_state="DISCOVERY",
            txn_id=None,
            source="project_lifecycle",
            reason=f"project {name!r} created",
            before=None,
            after={"name": name, "slug": slug, "seed_requirement": redacted_seed},
            session_id=session_id,
        ),
        events_path,
    )

    with path_lock(events_path):
        meta = read_project_meta(events_path)
        meta.update(
            name=name,
            profile=profile.model_dump(),
            workflow_state="DISCOVERY",
            created_at=created_at.isoformat(),
        )
        write_project_meta(events_path, meta)

    commit(
        project_dir,
        f"project created: {name}",
        paths=[".planning/events.ndjson", ".planning/project.json"],
    )

    return Project(
        slug=slug,
        name=name,
        profile=profile,
        workflow_state="DISCOVERY",
        created_at=created_at,
        path=project_dir,
    )


def open_project(slug: str, *, projects_root: Path | str = DEFAULT_PROJECTS_ROOT) -> Project:
    """Reconstruct a `Project` from `<projects_root>/<slug>/.planning/project.json`."""

    project_dir = Path(projects_root) / slug
    events_path = project_dir / ".planning" / "events.ndjson"
    if not events_path.exists():
        raise FileNotFoundError(f"no project at {project_dir}")

    meta = read_project_meta(events_path)
    missing = [field for field in _PROJECT_META_FIELDS if field not in meta]
    if missing:
        raise ValueError(f"project.json at {project_dir} is missing {missing}")

    return Project(
        slug=slug,
        name=meta["name"],
        profile=UserProfile.model_validate(meta["profile"]),
        workflow_state=meta["workflow_state"],
        created_at=datetime.fromisoformat(meta["created_at"]),
        path=project_dir,
    )


def list_projects(*, projects_root: Path | str = DEFAULT_PROJECTS_ROOT) -> list[Project]:
    """Every project under `projects_root` that has a fully-formed
    `project.json` — a partially scaffolded directory (e.g. a crash mid
    `create_project`, before `project.json` is written) is skipped rather
    than raising, since listing is a read, not a repair tool."""

    root = Path(projects_root)
    if not root.exists():
        return []

    projects: list[Project] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        events_path = entry / ".planning" / "events.ndjson"
        if not events_path.exists():
            continue
        try:
            projects.append(open_project(entry.name, projects_root=root))
        except ValueError:
            continue
    return projects
