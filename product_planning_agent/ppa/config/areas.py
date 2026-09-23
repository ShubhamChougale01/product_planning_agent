"""Coverage areas — the denominator for progress and the source of every
question (DESIGN.md §1.2, S1.4).

Twelve areas, declared as plain data so they are editable without touching
any engine logic (T10's coverage/readiness engines read this list, they don't
hard-code it). Criticality is deliberately **not** a field here — see
`ppa/config/profiles.py` — because whether an area is critical depends on who
is answering, not on the area itself.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AreaStatus(str, Enum):
    """Per-area coverage state (DESIGN.md §1.2). Always moves left to right;
    engines that recompute coverage (T10) own the transition logic, not this
    module — this is just the vocabulary."""

    UNTOUCHED = "UNTOUCHED"
    PARTIAL = "PARTIAL"
    SUFFICIENT = "SUFFICIENT"
    CONFIRMED = "CONFIRMED"


class CoverageArea(BaseModel):
    """One of the twelve areas discovery must cover before a plan is READY."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    description: str
    probe_hints: list[str] = Field(default_factory=list)


AREAS: list[CoverageArea] = [
    CoverageArea(
        key="problem",
        label="Problem",
        description="What problem this solves and for whom, in the user's own words.",
        probe_hints=["What breaks today without this?", "Who feels that pain first?"],
    ),
    CoverageArea(
        key="users",
        label="Users",
        description="Who uses this, and how their needs differ across roles.",
        probe_hints=["Who are the primary vs. secondary users?", "What do they do today instead?"],
    ),
    CoverageArea(
        key="jobs",
        label="Jobs to be done",
        description="The concrete tasks users are trying to accomplish.",
        probe_hints=["What does a user do step by step, start to finish?"],
    ),
    CoverageArea(
        key="scope_in",
        label="In scope",
        description="What v1 explicitly includes.",
        probe_hints=["What must ship for this to be usable at all?"],
    ),
    CoverageArea(
        key="scope_out",
        label="Out of scope",
        description="What is explicitly deferred, and why.",
        probe_hints=["What are you deliberately not building yet?"],
    ),
    CoverageArea(
        key="success",
        label="Success criteria",
        description="How anyone will know this worked.",
        probe_hints=["What number or outcome changes if this succeeds?"],
    ),
    CoverageArea(
        key="constraints",
        label="Constraints",
        description="Hard limits — budget, timeline, team, legal, compliance.",
        probe_hints=["What can't change no matter what?"],
    ),
    CoverageArea(
        key="existing_system",
        label="Existing system",
        description="What already exists that this must integrate with or replace.",
        probe_hints=["What's already running today that this touches?"],
    ),
    CoverageArea(
        key="platform",
        label="Platform",
        description="Target platforms, runtime environment, deployment surface.",
        probe_hints=["Web, mobile, both? On-prem or cloud?"],
    ),
    CoverageArea(
        key="data",
        label="Data",
        description="What data this reads, writes, owns, or must protect.",
        probe_hints=["Where does the data come from, and who owns it?"],
    ),
    CoverageArea(
        key="nfr",
        label="Non-functional requirements",
        description="Performance, security, availability, scale expectations.",
        probe_hints=["How many users/requests at peak?", "What uptime is required?"],
    ),
    CoverageArea(
        key="rollout",
        label="Rollout",
        description="How this reaches users — phased, big-bang, flagged.",
        probe_hints=["Big bang or phased rollout?", "Who sees this first?"],
    ),
]

AREA_KEYS: list[str] = [area.key for area in AREAS]
AREAS_BY_KEY: dict[str, CoverageArea] = {area.key: area for area in AREAS}
