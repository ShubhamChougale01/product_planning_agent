# T13 — ToolSpec contract and tool registry

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.9, S5.1, S5.3 |

## Prerequisites

- [x] **T05**

## Why this task exists

Tool descriptions are how the model decides what to call. Writing them as prose guarantees drift
and ambiguity. Making the description a structured dataclass means a test can assert every tool
is fully specified — ambiguity becomes a CI failure rather than a debugging session three weeks later.

## What to build

### ToolSpec — `ppa/tools/spec.py`

Thirteen mandatory fields (your eleven required elements, plus `name` and `purpose` as fields):

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    purpose: str
    inputs: dict[str, str]        # field -> type and meaning
    required: list[str]
    optional: list[str]
    formats: dict[str, str]       # field -> regex / enum / range
    returns: str                  # success shape
    examples: list[str]           # >= 2 realistic calls
    edge_cases: list[str]
    limitations: list[str]
    use_when: list[str]           # >= 2 explicit conditions
    do_not_use_when: list[str]    # >= 2 explicit conditions
    related_tools: dict[str, str] # name -> how this one differs
```

`render_description(spec) -> str` produces the text the model actually sees. One renderer, so
every tool description has identical structure.

### Registry — `ppa/tools/registry.py`

`register(spec, handler, owner_agents)`. Holds the agent→tool grant table. A tool with an
incomplete spec **fails registration** — not at call time, at import time.

### Tool server — `ppa/tools/server.py`  (S5.3)

The wiring that makes any of this callable from an agent.

Build the in-process MCP server with `create_sdk_mcp_server` and register each tool with the
`@tool` decorator, using the rendered `ToolSpec` description. In-process matters: the server runs
in the same Python process, so tools share ledger objects directly — no subprocess, no
serialization tax.

`server_for(agent_id)` returns a server exposing **only that agent's granted tools**, so
`allowed_tools` is derived from the grant table rather than hand-listed per agent.

Treat `allowed_tools` as a **hint to the model, not a security boundary**. The real enforcement is
the dispatcher check in T14, which runs regardless of what the model was told it could call.

### Worked example to follow

```
manage_linear_issue
  use_when:  · workflow_state == PLAN_APPROVED
             · the story passed validate_story
             · the story traces to a CONFIRMED requirement
  do_not_use_when:
             · plan is draft or in review        -> BUSINESS error
             · a blocking requirement is open    -> BUSINESS error
             · the user is still in Discovery    -> PERMISSION error
  related:   generate_story  - produces the story; pushes nothing
             validate_story  - checks a story; never creates an issue
```

## Files touched

```
ppa/tools/spec.py
ppa/tools/registry.py
ppa/tools/server.py
tests/test_tools/test_spec.py
```

## Done when

- [x] A test asserts **every** registered tool populates all thirteen fields
- [x] `use_when`, `do_not_use_when` and `examples` each have at least 2 entries per tool
- [x] Registering a tool with an incomplete spec raises at import time
- [x] `related_tools` names how each competing tool differs, not just that it exists
- [x] One renderer produces all descriptions — no hand-written description strings anywhere
- [x] `server_for(agent_id)` exposes exactly that agent's granted tools and nothing else
- [x] `allowed_tools` is derived from the grant table, never hand-listed per agent

## Build record

Built `ppa/tools/spec.py` (`ToolSpec`, `render_description`), `ppa/tools/registry.py` (`register`,
`get`, `all_tools`, `tools_for_agent`, `clear_registry`), and `ppa/tools/server.py` (`server_for`,
`granted_sdk_tools`, `allowed_tool_names`), wired to the real installed `claude-agent-sdk`'s
`create_sdk_mcp_server`/`tool` — inspected the installed package directly (signatures, docstrings)
rather than guessing its API.

`register()`'s validator goes a little beyond the task's literal thirteen-field-populated
requirement: it also cross-checks that `required ∪ optional == inputs.keys()` (disjoint) and that
every `formats` key names a real input — catching a spec author declaring an input but forgetting
to say whether it's required, which "all fields populated" alone wouldn't catch.

`ppa/tools/server.py`'s `input_schema` declares every field `str` regardless of `ToolSpec.formats`,
since `ToolSpec.inputs` values are prose ("field: str, meaning"), not machine-parseable types —
logged as decision #22; real per-field validation is deferred to T19 as designed (§2.10's five
validation layers), not lost.

`granted_sdk_tools(agent_id)` is exposed alongside `server_for` specifically so tests can assert
"exactly this agent's tools, nothing else" against the actual `SdkMcpTool` objects, without needing
to drive the full MCP transport to introspect a built server.

Tests: `tests/test_tools/test_spec.py` (6), `tests/test_tools/test_registry.py` (17),
`tests/test_tools/test_server.py` (6) — beyond the task's own "Files touched" list (which names only
`test_spec.py`), split by module to match this build's established convention. Full suite re-run:
**355 passed** (326 after T12, +29).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_tools/`
3. Commit: `git add -A && git commit -m "T13: ToolSpec contract and tool registry"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t13_*.md completed_tasks\
   bash:     mv tasks/t13_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T13` on the board.
