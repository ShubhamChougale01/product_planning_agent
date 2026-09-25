"""Layer 4 — semantic (DESIGN.md §2.13: "tool body").

Runs after workflow (a table lookup) precisely because semantic checks may
need to load related entities — §2.13's own stated reason for the
ordering. This module does not reimplement any tool's semantic rule
itself; it is a small registry so each rule can be declared once, next to
the tool that owns it, and still be discoverable and independently
testable from here.

`ppa.tools.discovery_tools` registers `manage_requirement(confirm)`'s rule
— a Requirement cannot be `CONFIRMED` while a blocking `Unknown` covering
the same area is still `OPEN` — at import time, the one semantic rule this
build needs so far. A tool with no registered check simply has nothing to
run at this layer; that is not an error, it means the tool has no
semantic-layer rule (yet).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ppa.ledger.models import BaseEntity
from ppa.results.envelope import ToolResult

LAYER = "semantic"

SemanticCheck = Callable[[Mapping[str, BaseEntity], BaseEntity, dict[str, Any]], "ToolResult | None"]

_CHECKS: dict[str, SemanticCheck] = {}


def register_check(tool_name: str, check_fn: SemanticCheck) -> None:
    """Declare `tool_name`'s semantic-layer rule. Called once, at the
    owning module's import time — the same convention `ppa/tools/
    registry.py::register` uses for tool registration itself."""

    _CHECKS[tool_name] = check_fn


def has_check(tool_name: str) -> bool:
    return tool_name in _CHECKS


def check(tool_name: str, entities: Mapping[str, BaseEntity], entity: BaseEntity, kwargs: dict[str, Any]) -> ToolResult | None:
    """Run `tool_name`'s registered semantic check, if any. `None` both
    when the check passes and when no check is registered for this tool —
    callers that need to distinguish the two should call `has_check` first."""

    check_fn = _CHECKS.get(tool_name)
    if check_fn is None:
        return None
    return check_fn(entities, entity, kwargs)
