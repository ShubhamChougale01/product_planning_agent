I want to design a product plan agent. when i give you a topic, you should fist ask me clarifying questions about scope, audience, and desired depth. Then form a written plan. once i approve the plan you research the topic thoroughly organize your findings into clear sections and save a structured report to the output folder before we build this show me your plan for agent itself

                Product Planning Agent
                ORCHESTRATOR
		               │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
       V1 Agent        V2 Agent        V3 Agent
     Understand         Plan           Execute
          │              │              │
     Gather info     Create plan    Generate stories
     Clarify         Milestones     Features
     Research        Timeline       Bugs
     Decisions       Review         Linear
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                 Planning Ledger

V1                    V2                    V3

UNDERSTAND     →      PLAN            →     EXECUTE
Gather                Design                Stories
Clarify               Milestones            Linear
Research              Timeline              Tasks
Decide                Review                Bugs
Ledger                Approve               Features

|Role|Agent name|Responsibility|
|---|---|---|
|Main coordinator|**Orchestrator**|Decides which phase/agent should act|
|V1|**Discovery Agent**|Understands, clarifies, researches, tracks decisions|
|V2|**Planning Agent**|Creates, validates, versions the product plan|
|V3|**Delivery Agent**|Converts approved plans into stories/tasks and Linear issues|

**Discovery Agent**

```
ask_question
classify_unknown
guidance
research
manage_requirements
manage_assumptions
manage_decisions
get_status
```

**Planning Agent**

```
read_ledger
analyze_requirements
create_plan
manage_milestones
manage_timeline
impact_analysis
plan_review
```

**Delivery Agent**

```
read_approved_plan
generate_story
validate_story
create_linear_issue
update_linear_issue
```

**Orchestrator**

```
get_planning_status
invoke_discovery
invoke_planning
invoke_delivery
```

**4 layers of guardrails**.
### 1. Agent-level guardrails

Each agent gets a strict responsibility boundary.

```
ORCHESTRATOR
→ route only
→ no direct requirement editing
→ no story generation

DISCOVERY
→ understand + clarify
→ no product plan
→ no Linear issues

PLANNING
→ plan + validate
→ no discovery questions unless explicitly returned to Discovery
→ no Linear issues

DELIVERY
→ stories + Linear
→ cannot modify approved requirements
→ cannot create stories from an unapproved plan
```

### 2. Tool-level guardrails

Don't just tell agents what **not** to do.

Physically restrict their available tools.

```
DiscoveryAgent
    ├── ask_question ✓
    ├── guidance ✓
    ├── research ✓
    ├── update_requirement ✓
    └── create_linear_issue ✗

PlanningAgent
    ├── read_ledger ✓
    ├── create_plan ✓
    ├── timeline ✓
    └── create_linear_issue ✗

DeliveryAgent
    ├── read_approved_plan ✓
    ├── generate_story ✓
    ├── create_linear_issue ✓
    └── modify_requirement ✗
```

This is one of the strongest protections.

### 3. State / workflow guardrails

The agent **cannot skip phases**.

For example:

```
DISCOVERY
   ↓
DISCOVERY_COMPLETE
   ↓
PLANNING
   ↓
PLAN_REVIEW
   ↓
PLAN_APPROVED
   ↓
DELIVERY
```

So this should be impossible:

```
User: "Build me a payment system."

Discovery Agent
       ↓
"Here are 20 Linear tickets."
```

Instead:

```
Requirement
   ↓
Discovery
   ↓
Unknowns resolved / documented
   ↓
Planning
   ↓
Plan approved
   ↓
Delivery
   ↓
Linear
```

### 4. Data guardrails

Every important piece of information should carry metadata.

For example:

```
Requirement
├── id
├── version
├── status
├── confidence
├── source
├── created_at
├── updated_at
└── supersedes

Decision
├── id
├── status
├── decision_date
├── expected_decision_date
├── decided_by
└── rationale

Assumption
├── id
├── statement
├── confidence
├── impact
├── status
└── requires_confirmation
```

This prevents the LLM from silently turning:

> "I think we'll probably support mobile"

into:

> "Mobile support is a confirmed requirement."

## The most important guardrail

I'd make this a **global rule for the entire system**:

> **The agent must never silently invent, promote, delete, or overwrite product decisions.**

Instead:

```
Unknown
   ↓
Assumption
   ↓
User confirmation / Research
   ↓
Confirmed Requirement
```

And:

```
Decide later
   ↓
OPEN_DECISION
   ↓
Decision made
   ↓
RESOLVED
```

Every transition gets recorded in the Ledger.

### Human approval gates

Since you chose a **semi-autonomous** agent, I'd have explicit approval gates:

```
             ┌──────────────┐
             │  DISCOVERY   │
             └──────┬───────┘
                    ↓
          Critical requirements?
                    ↓
             HUMAN REVIEW
                    ↓
             ┌──────────────┐
             │   PLANNING   │
             └──────┬───────┘
                    ↓
                PLAN REVIEW
                    ↓
             HUMAN APPROVAL
                    ↓
             ┌──────────────┐
             │   DELIVERY   │
             └──────┬───────┘
                    ↓
                  LINEAR
```

So **V3 cannot create Linear stories simply because the model thinks the plan is good enough**. It needs the required approval state in the Ledger.

**Every tool call should be auditable.**

Something like:

```
Agent: ProductDiscoveryAgent
Tool: guidance
Input: requirement_id=REQ-001
Reason: USER_SELECTED_I_DONT_KNOW
Result: GUIDANCE_COMPLETED
Timestamp: ...
```

That gives us:

**Agent identity → allowed tool → reason → input → result → Ledger change**

This will make debugging the agent _much_ easier.

# complete architecture checklist:

| Layer                             | What we have | Needed                                   |
| --------------------------------- | ------------ | ---------------------------------------- |
| **1. Orchestrator**               | ✅            | Main coordinator/routing                 |
| **2. Subagents**                  | ✅            | Discovery, Planning, Delivery            |
| **3. Tools**                      | ✅            | Agent-specific tools                     |
| **4. Tool permissions**           | ✅            | Prevent wrong-tool usage                 |
| **5. Guardrails**                 | ✅            | Behavioral + structural safety           |
| **6. Planning Ledger**            | ✅            | Source of truth                          |
| **7. State machine**              | ✅            | Controls phase transitions               |
| **8. Human approval gates**       | ✅            | Critical decisions + plan approval       |
| **9. Requirement versioning**     | ✅            | History and change tracking              |
| **10. Decision management**       | ✅            | Decide now / later / unresolved          |
| **11. Assumption management**     | ✅            | No silent assumptions                    |
| **12. Research**                  | ✅            | Research unknowns                        |
| **13. Change / impact analysis**  | ✅            | Understand consequences of changes       |
| **14. Audit trail**               | ✅            | Track agent/tool actions                 |
| **15. Error handling / recovery** | ✅            | Need to explicitly design                |
| **16. Context management**        | ✅            | Need to explicitly design                |
| **17. Evaluation / testing**      | ✅            | Need to explicitly design                |
| **18. Observability**             | ✅            | Logs, metrics, traces                    |
| **19. Security / permissions**    | ✅            | Especially once Linear/API access exists |
| **20. External integrations**     | V3           | Linear/MCP/API                           |

                         USER
                          │
                          ▼
                  ┌───────────────┐
                  │ ORCHESTRATOR  │
                  └───────┬───────┘
                          │
                  STATE / ROUTING
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     DISCOVERY         PLANNING        DELIVERY
      AGENT             AGENT           AGENT
          │               │               │
     ┌────┴────┐     ┌────┴────┐     ┌────┴────┐
     │  Tools  │     │  Tools  │     │  Tools  │
     └────┬────┘     └────┬────┘     └────┬────┘
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                  ┌───────────────┐
                  │    LEDGER     │
                  │ Source of     │
                  │ Truth         │
                  └───────┬───────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   Versioning        Decisions         Assumptions
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                 CHANGE / IMPACT
                       ANALYSIS
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
       AUDIT           OBSERVABILITY    EVALUATION
                          │
                          ▼
                    ERROR / RECOVERY
                          │
                          ▼
                 HUMAN APPROVAL
                          │
                          ▼
                    EXTERNAL TOOLS
                       (Linear)