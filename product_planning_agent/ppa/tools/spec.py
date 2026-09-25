"""ToolSpec — the thirteen-element tool description contract (DESIGN.md
§2.9, S5.1).

Tool descriptions are how the model decides what to call. Writing them as
prose guarantees drift and ambiguity between tools, and between a tool and
its own behavior over time. A `ToolSpec` is a plain data container instead —
`ppa/tools/registry.py::register` is what actually enforces every field is
populated, at import time, not here. This module owns only the shape of the
contract and the one renderer that turns it into the text the model sees.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolSpec:
    """The eleven required elements of a tool description, plus `name` and
    `purpose` as fields of their own — thirteen in total, matching DESIGN.md
    §2.9 exactly. Every field below is meant to be populated for every real
    tool; `ppa/tools/registry.py::register` is what actually checks that."""

    name: str
    purpose: str
    inputs: dict[str, str] = field(default_factory=dict)
    """field name -> its type and meaning, e.g. `"project_slug": "str, the
    project's slug as returned by create_project"`."""
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    formats: dict[str, str] = field(default_factory=dict)
    """field name -> a regex, enum, or range describing legal values —
    only for fields where "a string" or "an int" isn't precise enough."""
    returns: str = ""
    """The success shape — what the caller gets back when this works."""
    examples: list[str] = field(default_factory=list)
    """>= 2 realistic calls, enforced at registration."""
    edge_cases: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    use_when: list[str] = field(default_factory=list)
    """>= 2 explicit conditions, enforced at registration."""
    do_not_use_when: list[str] = field(default_factory=list)
    """>= 2 explicit conditions, enforced at registration — each naming the
    error category the model should expect, per the worked example."""
    related_tools: dict[str, str] = field(default_factory=dict)
    """other tool name -> how this one differs, never just "see also"."""


def _format_bullets(items: list[str], indent: str) -> str:
    return "\n".join(f"{indent}\xb7 {item}" for item in items)


def render_description(spec: ToolSpec) -> str:
    """The one renderer. Every tool's description the model actually sees
    comes from calling this on its `ToolSpec` — there is no other place in
    this codebase that hand-writes a tool description string."""

    lines: list[str] = [spec.name, f"  purpose: {spec.purpose}", "", "  inputs:"]

    for input_name, meaning in spec.inputs.items():
        marker = "required" if input_name in spec.required else "optional"
        line = f"    - {input_name} ({marker}): {meaning}"
        if input_name in spec.formats:
            line += f" [format: {spec.formats[input_name]}]"
        lines.append(line)
    if not spec.inputs:
        lines.append("    (none)")

    lines.append("")
    lines.append(f"  returns: {spec.returns}")

    lines.append("")
    lines.append("  examples:")
    lines.append(_format_bullets(spec.examples, "    "))

    lines.append("")
    lines.append("  edge_cases:")
    lines.append(_format_bullets(spec.edge_cases, "    "))

    lines.append("")
    lines.append("  limitations:")
    lines.append(_format_bullets(spec.limitations, "    "))

    lines.append("")
    lines.append("  use_when:")
    lines.append(_format_bullets(spec.use_when, "    "))

    lines.append("")
    lines.append("  do_not_use_when:")
    lines.append(_format_bullets(spec.do_not_use_when, "    "))

    lines.append("")
    lines.append("  related_tools:")
    for other_name, distinction in spec.related_tools.items():
        lines.append(f"    - {other_name}: {distinction}")
    if not spec.related_tools:
        lines.append("    (none)")

    return "\n".join(lines)
