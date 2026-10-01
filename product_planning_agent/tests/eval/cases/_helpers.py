"""Shared plumbing for the eighteen S12.2 cases — one real project per
case, the same `_profile`/writer-kwargs shape every other `tests/eval/*.py`
module already uses (`test_clarify.py`, `test_dont_know.py`), so a case
reads the same way the rest of this package does rather than inventing its
own idiom.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.config.profiles import UserProfile
from ppa.ledger.project import Project, create_project

NOW = datetime(2026, 9, 30, 9, 0, 0, tzinfo=timezone.utc)


def profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def make_project(tmp_path, name: str = "Eval Case Project") -> Project:
    return create_project(name, "seed requirement for an eval case", profile(), projects_root=tmp_path / "projects")


def writer_kwargs(**overrides) -> dict:
    base = dict(actor_id="agent:discovery", session_id="eval-case", now=NOW)
    base.update(overrides)
    return base
