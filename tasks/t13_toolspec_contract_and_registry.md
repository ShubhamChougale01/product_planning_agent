# T13 — ToolSpec contract and tool registry

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.9, S5.1, S5.3 |

## Prerequisites

- [ ] **T05**

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

- [ ] A test asserts **every** registered tool populates all thirteen fields
- [ ] `use_when`, `do_not_use_when` and `examples` each have at least 2 entries per tool
- [ ] Registering a tool with an incomplete spec raises at import time
- [ ] `related_tools` names how each competing tool differs, not just that it exists
- [ ] One renderer produces all descriptions — no hand-written description strings anywhere
- [ ] `server_for(agent_id)` exposes exactly that agent's granted tools and nothing else
- [ ] `allowed_tools` is derived from the grant table, never hand-listed per agent

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
