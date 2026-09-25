# T14 — Permission gate and dispatcher

| | |
|---|---|
| **Phase** | B · Tools and permissions |
| **Estimate** | 0.5 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.10, §2.13, S5.2 |

## Prerequisites

- [x] **T13**

## Why this task exists

Least privilege only means something if it is enforced in code. A prompt saying "you must not
create Linear issues" is a suggestion; a dispatcher that refuses to run the handler is a boundary.
The caller identity must come from the invocation context, never from anything the model says.

## What to build

### Dispatcher — `ppa/tools/dispatch.py`

```python
def dispatch(tool_name, args, ctx: InvocationContext) -> ToolResult:
    # 1. PERMISSION — first, always
    if tool_name not in registry.grant_for(ctx.agent_id):
        return permission_error(tool_name, ctx.agent_id)
    # ... remaining layers wired in T19
```

`ctx.agent_id` is set by the orchestrator when it invokes an agent. **It is never read from model
output.** A model claiming to be the Delivery Agent changes nothing.

Permission runs **first** — before schema — for two reasons: it is the cheapest check, and a
permission failure should not leak schema details about a tool the caller may not use.

### Grants

| Agent | Tools |
|---|---|
| Orchestrator | `read_workflow_state` `invoke_discovery` `invoke_planning` `invoke_delivery` `review_subagent_result` |
| Discovery | `read_planning_state` `manage_requirement` `manage_assumption` `manage_decision` `manage_unknown` `ask_user` `request_guidance` |
| Guidance subagent | `read_planning_state` `manage_research` |
| Research subagent | `read_planning_state` `manage_research` (+ web search) |
| Planning *(v2 stub)* | `read_planning_state` `manage_plan` `manage_milestone` `manage_timeline` `analyze_plan_impact` |
| Delivery *(v3 stub)* | `read_approved_plan` `generate_story` `validate_story` `manage_linear_issue` `read_planning_state` |

Every rejection is written to `audit.ndjson` with the attempted tool and calling agent.

## Files touched

```
ppa/tools/dispatch.py
ppa/agents/registry.py
tests/test_permissions/test_grants.py
```

## Done when

- [x] A test enumerates **every** (agent, tool) pair against the grant table
- [x] Discovery calling `manage_linear_issue` returns PERMISSION and the handler body never runs — assert with a spy
- [x] Delivery calling `manage_requirement` returns PERMISSION
- [x] Caller identity cannot be influenced by tool arguments — test with a hostile `agent_id` in args
- [x] Permission is checked before schema validation — a malformed call from an ungranted agent yields PERMISSION, not VALIDATION
- [x] Every rejection appears in the audit log

## Build record

Built `ppa/agents/registry.py` (`GRANTS`, `grant_for` — the static agent -> tool table, verbatim from
this task's own table) and `ppa/tools/dispatch.py` (`InvocationContext`, `dispatch`,
`permission_error`). `dispatch` is `async def` (tool handlers are async per the SDK contract from
T13); tests call it via `asyncio.run(...)` in plain sync test functions rather than declaring
`async def test_...`, since no async pytest plugin mode is configured in this project and an
unmarked async test silently never runs its body — a dangerous way to test a permission boundary.

Beyond the permission check itself, `dispatch` also distinguishes a granted-but-not-yet-registered
tool (most tools, before T15-T18 build them) as `NOT_IMPLEMENTED` rather than crashing — using the
error taxonomy T05 already built for exactly this case. A granted-and-registered call executes the
real handler and is audited too (`operation` inferred as `read`/`write` from the tool name's own
`read_*` prefix convention, since `ToolSpec` carries nothing more precise to key on yet).

`ppa/agents/registry.py`'s stub docstring incorrectly said "filled in by T20" (logged as decision
#23, same root cause as blockers #2/#3) — T14 is the file's actual first task; T20 only extends it.

Tests: `tests/test_permissions/test_grants.py`, 15 test functions (136 collected once
the every-(agent,tool)-pair parametrization expands). Full suite re-run: **491 passed**
(355 after T13, +136).

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_permissions/`
3. Commit: `git add -A && git commit -m "T14: Permission gate and dispatcher"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t14_*.md completed_tasks\
   bash:     mv tasks/t14_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T14` on the board.
