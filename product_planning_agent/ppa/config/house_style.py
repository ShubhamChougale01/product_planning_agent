"""House style configuration — templates at the edge, never in the core
schema (DESIGN.md §6.3, S1.6).

The canonical ledger schema (`ppa/ledger/models.py`) never changes to
accommodate a client's paperwork. Style is three things at the boundary:

1. An export/render mapping — canonical entity -> template shape, applied on
   output only.
2. `custom_fields: dict[str, Any]` on the entity, validated against whichever
   style config is active. Org-required fields live here, never as new
   top-level schema — that's the whole point of the seam.
3. A terminology map — a label swap, not a rename in code.

**Resolved 2026-09-23 (`tasks/readme.md` open decision #1): no existing
Coditas templates.** The default shipped below is ours, designed to be
replaced — `required_custom_fields` ships empty because nothing is required
yet, not because the mechanism doesn't exist (T04's own instruction: ship the
seam before anything needs it).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field

from ppa.ledger.models import Requirement

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
DEFAULT_HOUSE_STYLE_PATH = CONFIG_DIR / "house_style.yaml"


class RequirementStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_custom_fields: list[str] = Field(default_factory=list)
    template: str


class StoryStyle(BaseModel):
    """v3 shape, defined now so v1 doesn't block it (DESIGN.md §6.3) — nothing
    in v1 writes a story yet, so this is declared but unused."""

    model_config = ConfigDict(extra="forbid")

    template: str
    fields: list[str] = Field(default_factory=list)


class ExportStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["markdown", "json", "jira_csv"]


class HouseStyle(BaseModel):
    """The whole of `config/house_style.yaml`, validated. Nothing here may
    ever require a change to `ppa/ledger/models.py` — that's the seam."""

    model_config = ConfigDict(extra="forbid")

    name: str
    terminology: dict[str, str] = Field(default_factory=dict)
    requirement: RequirementStyle
    story: StoryStyle | None = None
    export: ExportStyle


class MissingRequiredCustomFields(ValueError):
    """Raised when an entity's `custom_fields` is missing a field the active
    house style declares required."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"custom_fields is missing required field(s): {', '.join(missing)}")


def load_house_style(path: Path | str = DEFAULT_HOUSE_STYLE_PATH) -> HouseStyle:
    """Load and validate a house style config. Swapping `path` for a
    different file is the entire mechanism for adopting a client's style —
    no code change, per §6.3."""

    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return HouseStyle.model_validate(data)


def validate_custom_fields(custom_fields: dict[str, Any], style: HouseStyle) -> None:
    """Raise `MissingRequiredCustomFields` unless every field named in
    `style.requirement.required_custom_fields` is present in `custom_fields`.
    An empty `required_custom_fields` — the shipped default — always passes:
    the seam exists before anything needs it, it doesn't require anything by
    default."""

    missing = [f for f in style.requirement.required_custom_fields if f not in custom_fields]
    if missing:
        raise MissingRequiredCustomFields(missing)


def render_requirement(
    requirement: Requirement,
    style: HouseStyle,
    templates_dir: Path | str | None = None,
) -> str:
    """Render `requirement` through the template `style.requirement.template`
    names, using `style.terminology` for labels. Swapping `style` for one
    naming a different template or a different terminology map changes the
    rendered output with zero change to `ppa/ledger/models.py` — that's the
    Done-when this function exists to satisfy.
    """

    base_dir = Path(templates_dir) if templates_dir is not None else CONFIG_DIR
    env = Environment(
        loader=FileSystemLoader(str(base_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(style.requirement.template)
    return template.render(
        requirement=requirement.model_dump(mode="json"),
        terminology=style.terminology,
    )
