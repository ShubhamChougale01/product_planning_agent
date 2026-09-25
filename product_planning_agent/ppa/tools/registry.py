"""Tool registry — the agent -> tool grant table (DESIGN.md §2.9, §2.10,
S5.1, S5.2).

`register()` is the one place a tool becomes callable, and it is also the
one place an incomplete `ToolSpec` becomes a hard failure. Real tool modules
(T15+) call `register()` at module import time — a top-level statement, not
inside a function — so a missing `use_when` entry breaks `import
ppa.tools.discovery_tools`, not a debugging session three weeks later.

This module owns *registration and lookup* only. Whether a call is actually
permitted for the agent making it is T14's dispatcher, checked again at
call time — `owner_agents` here is data the dispatcher (and
`ppa/tools/server.py`'s `server_for`) reads, never itself an enforcement
point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ppa.tools.spec import ToolSpec

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler
    owner_agents: frozenset[str]


_REGISTRY: dict[str, RegisteredTool] = {}

_MIN_EXAMPLES = 2
_MIN_USE_WHEN = 2
_MIN_DO_NOT_USE_WHEN = 2


def _validate_spec(spec: ToolSpec) -> None:
    """Every violation is collected and reported together — a spec author
    fixing one field at a time from a partial error would burn as much
    wall-clock as the "debugging session three weeks later" this whole
    contract exists to avoid."""

    errors: list[str] = []

    if not spec.name.strip():
        errors.append("name must be non-empty")
    if not spec.purpose.strip():
        errors.append("purpose must be non-empty")
    if not spec.returns.strip():
        errors.append("returns must be non-empty")

    input_keys = set(spec.inputs)
    required_set = set(spec.required)
    optional_set = set(spec.optional)
    if required_set & optional_set:
        errors.append(
            f"fields cannot be both required and optional: {sorted(required_set & optional_set)}"
        )
    if (required_set | optional_set) != input_keys:
        missing = input_keys - (required_set | optional_set)
        extra = (required_set | optional_set) - input_keys
        if missing:
            errors.append(f"inputs missing from required/optional: {sorted(missing)}")
        if extra:
            errors.append(f"required/optional names fields not in inputs: {sorted(extra)}")

    unknown_format_fields = set(spec.formats) - input_keys
    if unknown_format_fields:
        errors.append(f"formats names fields not in inputs: {sorted(unknown_format_fields)}")

    if len(spec.examples) < _MIN_EXAMPLES:
        errors.append(f"examples needs >= {_MIN_EXAMPLES} entries, got {len(spec.examples)}")
    if len(spec.use_when) < _MIN_USE_WHEN:
        errors.append(f"use_when needs >= {_MIN_USE_WHEN} entries, got {len(spec.use_when)}")
    if len(spec.do_not_use_when) < _MIN_DO_NOT_USE_WHEN:
        errors.append(
            f"do_not_use_when needs >= {_MIN_DO_NOT_USE_WHEN} entries, got {len(spec.do_not_use_when)}"
        )
    if not spec.edge_cases:
        errors.append("edge_cases must have at least one entry")
    if not spec.limitations:
        errors.append("limitations must have at least one entry")
    if not spec.related_tools:
        errors.append("related_tools must have at least one entry")

    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"ToolSpec {spec.name!r} is incomplete: {joined}")


def register(spec: ToolSpec, handler: ToolHandler, owner_agents: list[str]) -> RegisteredTool:
    """Validate `spec`, then register `handler` under `spec.name`, granted
    to every agent id in `owner_agents`. Raises immediately on an incomplete
    spec, a duplicate name, or an empty `owner_agents` — a tool nobody may
    call is not a tool, it's dead code with a description."""

    _validate_spec(spec)
    if not owner_agents:
        raise ValueError(f"ToolSpec {spec.name!r}: owner_agents must name at least one agent")
    if spec.name in _REGISTRY:
        raise ValueError(f"a tool named {spec.name!r} is already registered")

    registered = RegisteredTool(spec=spec, handler=handler, owner_agents=frozenset(owner_agents))
    _REGISTRY[spec.name] = registered
    return registered


def get(name: str) -> RegisteredTool:
    return _REGISTRY[name]


def all_tools() -> list[RegisteredTool]:
    return list(_REGISTRY.values())


def tools_for_agent(agent_id: str) -> list[RegisteredTool]:
    """Every tool granted to `agent_id` — the single source `server_for`
    (`ppa/tools/server.py`) and T14's dispatcher both read from, so
    `allowed_tools` is always derived from this table, never hand-listed."""

    return [t for t in _REGISTRY.values() if agent_id in t.owner_agents]


def clear_registry() -> None:
    """Test-only. Production code never calls this — real tool modules
    register once at import time and stay registered for the process's
    life, same as any other module-level side effect.

    **Prefer `snapshot`/`restore` over a bare `clear_registry()` in a test
    fixture.** Python only runs a module's top-level `register()` call once,
    the first time it is ever imported — so if some other already-imported
    module (a real `ppa.tools.discovery_tools`, say) registered a tool
    before this test session got to it, a bare `clear_registry()` erases
    that registration permanently: nothing will ever re-run the import to
    put it back. `snapshot`/`restore` isolates a test's own fake
    registrations without destroying real ones that happened to exist
    first."""

    _REGISTRY.clear()


def snapshot() -> dict[str, RegisteredTool]:
    """A shallow copy of the current registry, for a test fixture to
    restore after clearing — see `clear_registry`'s own docstring for why
    this is the safer default over a bare clear."""

    return dict(_REGISTRY)


def restore(saved: dict[str, RegisteredTool]) -> None:
    _REGISTRY.clear()
    _REGISTRY.update(saved)
