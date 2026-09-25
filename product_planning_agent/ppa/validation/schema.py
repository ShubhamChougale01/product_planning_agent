"""Layer 2 — schema (DESIGN.md §2.13: "PreToolUse hook (Pydantic)").

Generic, `ToolSpec`-driven checking: every field named in `spec.required`
must be present and non-blank, and every field whose `spec.formats` entry
reads `"one of: a, b, c"` must actually be one of those tokens when
supplied. This is deliberately shallow — it is the check a *dispatcher* can
run for *any* registered tool without knowing anything about that tool's
domain, which is exactly what makes it reusable across every tool T13's
registry ever accepts.

**This does not replace a writer's own deeper schema validation.** T16's
`manage_requirement(create)` rejecting a `covers_areas=[]` with a message
naming every valid area key, or T17's `ask_user` rejecting a 6-question
batch, are richer checks than this generic layer can express from a
`ToolSpec` alone — they stay in the tool body, per §2.13's own note that
"semantic validation may need to load related entities." This module is
the floor every tool gets for free, not the ceiling.
"""

from __future__ import annotations

import re
from typing import Any

from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult
from ppa.tools.spec import ToolSpec

LAYER = "schema"

_ONE_OF = re.compile(r"one of:\s*(.+)", re.IGNORECASE)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _reject(tool_name: str, code: str, description: str) -> ToolResult:
    rule = CATEGORY_RULES[ErrorCategory.VALIDATION]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.VALIDATION,
            code=code,
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=f"{tool_name}: {description}",
            context={"validation_layer_failed": LAYER},
        ),
    )


def check(spec: ToolSpec, args: dict[str, Any]) -> ToolResult | None:
    """`None` if `args` satisfies `spec.required` and every recognized
    `"one of: ..."` format in `spec.formats`; otherwise a `VALIDATION`
    `ToolResult` naming the first field that failed."""

    for field in spec.required:
        if field not in args or _is_blank(args[field]):
            return _reject(spec.name, "MISSING_REQUIRED_FIELD", f"requires {field!r}")

    for field, fmt in spec.formats.items():
        if field not in args or args[field] is None:
            continue
        match = _ONE_OF.match(fmt)
        if not match:
            continue
        allowed = {token.strip() for token in match.group(1).split(",")}
        if str(args[field]) not in allowed:
            return _reject(
                spec.name, "INVALID_FORMAT",
                f"{field}={args[field]!r} is not one of {sorted(allowed)}",
            )

    return None
