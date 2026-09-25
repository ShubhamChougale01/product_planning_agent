"""Tool server — the in-process MCP wiring that makes a registered tool
callable from an agent (DESIGN.md §2.9, §2.18, S5.3).

In-process matters: `create_sdk_mcp_server` runs the server in the same
Python process as the rest of the ledger, so a tool handler shares ledger
objects directly — no subprocess boundary, no serialization tax.

`server_for(agent_id)` derives its tool list from
`ppa/tools/registry.py::tools_for_agent` alone — never a hand-written list
per agent. **`allowed_tools` is a hint to the model, not a security
boundary** (§2.10): the real enforcement is T14's dispatcher, which checks
the same grant table again at call time regardless of what the model was
told it could call.
"""

from __future__ import annotations

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server
from claude_agent_sdk import tool as sdk_tool

from ppa.tools.registry import RegisteredTool, tools_for_agent
from ppa.tools.spec import render_description


def _sdk_input_schema(spec_inputs: dict[str, str]) -> dict[str, type]:
    """`ToolSpec.inputs` maps a field name to a *description* ("str, the
    project's slug"), not an actual Python type — there is no reliable way
    to parse a real type back out of that prose. Every field is therefore
    declared `str` to the SDK's own (permissive) schema check; the real
    per-field type/format enforcement is validation layer 2
    (`ppa/validation/schema.py`, T19), which reads `ToolSpec.formats`
    directly rather than trusting whatever the SDK's generic schema allowed
    through. This is a deliberate simplification, not an oversight — see
    `blockers.md` for the reasoning."""

    return {name: str for name in spec_inputs}


def _wrap(registered: RegisteredTool) -> SdkMcpTool:
    return sdk_tool(
        registered.spec.name,
        render_description(registered.spec),
        _sdk_input_schema(registered.spec.inputs),
    )(registered.handler)


def granted_sdk_tools(agent_id: str) -> list[SdkMcpTool]:
    """The `SdkMcpTool` objects `server_for` builds its server from —
    exposed on its own so tests can assert exactly what an agent's server
    would expose without having to drive the full MCP transport to find
    out. `server_for` and this function read the same
    `tools_for_agent(agent_id)` call, so they can never disagree."""

    return [_wrap(t) for t in tools_for_agent(agent_id)]


def server_for(agent_id: str, *, server_name: str | None = None) -> McpSdkServerConfig:
    """An in-process MCP server exposing exactly `agent_id`'s granted
    tools — nothing more, nothing hand-picked."""

    return create_sdk_mcp_server(
        name=server_name or f"{agent_id}-tools",
        tools=granted_sdk_tools(agent_id),
    )


def allowed_tool_names(agent_id: str) -> list[str]:
    """The names to pass as `ClaudeAgentOptions.allowed_tools` — derived
    from the same grant table `server_for` reads, so the hint the model
    gets and the tools actually wired up can never drift apart."""

    return [t.spec.name for t in tools_for_agent(agent_id)]
