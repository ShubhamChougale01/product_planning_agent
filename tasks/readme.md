# Build board — Product Planning Agent

**35 tasks · ~27.5 days.** Source of truth for *what* and *why* is `DESIGN.md`.
These files are the *how*, in order. Each is self-contained: you should not need to
read DESIGN.md to execute one, only to understand the wider system.

## How to work the board

1. Pick the lowest-numbered task in `tasks/` (they sort in build order) whose prerequisites are all in `completed_tasks/`.
2. Do it. Tick every **Done when** box.
3. Move the file to `completed_tasks/` and tick it below.
4. If you discover the task was wrong, **edit the task file before moving it** — it becomes the record of what was actually built.

Tasks marked **no model** need no API calls and no Claude Code session — they are plain Python with `pytest`. That is most of the first two phases, deliberately.

## Board

### A · Foundation (no model, no cost)  ·  7.5d

| | Task | Est | Model |
|---|---|---|---|
| ☑ | `t01_environment_and_model_seam.md` Environment, scaffold and the model seam | 0.5 day | One 10-line script |
| ☑ | `t02_domain_entities_and_status_model.md` Domain entities and the status model | 0.75 day | No |
| ☑ | `t03_event_model_and_transactions.md` Event model and transaction envelope | 0.5 day | No |
| ☑ | `t04_config_areas_profiles_house_style.md` Configuration: coverage areas, user profiles, house style | 0.75 day | No |
| ☑ | `t05_result_envelope_and_errors.md` Result envelope and error taxonomy | 0.5 day | No |
| ☐ | `t06_event_log_and_secret_scanning.md` Event log with inbound secret scanning | 0.75 day | No |
| ☐ | `t07_materializer_ids_idempotency.md` Materializer, ID allocation, idempotency | 0.75 day | No |
| ☐ | `t08_project_lifecycle_audit_git.md` Project lifecycle, audit log, git | 0.5 day | No |
| ☐ | `t09_digest_projection.md` Digest projection | 0.5 day | No |
| ☐ | `t10_coverage_and_readiness_engines.md` Coverage and readiness engines | 0.75 day | No |
| ☐ | `t11_impact_graph_and_conflicts.md` Impact graph and conflict detection | 0.75 day | No |
| ☐ | `t12_date_rules_and_open_items.md` Date rules and open items | 0.5 day | No |

### B · Tools and permissions  ·  4.75d

| | Task | Est | Model |
|---|---|---|---|
| ☐ | `t13_toolspec_contract_and_registry.md` ToolSpec contract and tool registry | 1 day | No |
| ☐ | `t14_permission_gate_and_dispatcher.md` Permission gate and dispatcher | 0.5 day | No |
| ☐ | `t15_read_planning_state_tool.md` read_planning_state — the consolidated reader | 0.5 day | No |
| ☐ | `t16_manage_writer_tools.md` The manage_* writers | 1 day | No |
| ☐ | `t17_ask_user_tool.md` ask_user and the four affordances | 0.5 day | No |
| ☐ | `t18_stub_tools_and_approval_gate.md` Stub tools and the approval gate | 0.75 day | No |
| ☐ | `t19_validation_layer_wiring.md` Validation layer wiring | 0.5 day | No |

### C · Orchestration and guardrails  ·  2.25d

| | Task | Est | Model |
|---|---|---|---|
| ☐ | `t20_agent_protocol_and_workflow.md` Agent protocol and workflow state machine | 0.75 day | No |
| ☐ | `t21_preconditions_and_outer_loop.md` Preconditions and the outer loop | 1 day | Yes — first agent invocation |
| ☐ | `t22_guardrail_suite.md` Guardrail suite | 0.5 day | No |

### D · Discovery Agent — the intelligence layer  ·  6d

| | Task | Est | Model |
|---|---|---|---|
| ☐ | `t23_discovery_prompt_and_modes.md` Discovery system prompt and internal modes | 1 day | Yes |
| ☐ | `t24_intake_mode.md` Intake mode — the opening move | 0.5 day | Yes |
| ☐ | `t25_clarify_mode_question_engine.md` Clarify mode and the question engine | 1 day | Yes |
| ☐ | `t26_dont_know_routing.md` \"I don't know\" classification and routing | 1 day | Yes |
| ☐ | `t27_external_input_questionnaire.md` External input routing and the client questionnaire | 0.5 day | Yes |
| ☐ | `t28_guidance_subagent.md` Guidance Mode subagent | 1.25 day | Yes + web |
| ☐ | `t29_research_and_degradation.md` Research mode and provider degradation | 0.75 day | Yes + web |

### E · Product surface  ·  2d

| | Task | Est | Model |
|---|---|---|---|
| ☐ | `t30_review_and_change_handling.md` Review mode and change handling | 1 day | Yes |
| ☐ | `t31_cli_and_status_board.md` CLI and status board | 1 day | No |

### F · Resilience and validation  ·  5d

| | Task | Est | Model |
|---|---|---|---|
| ☐ | `t32_transactions_retry_recovery.md` Transactions, retry, recovery and escalation | 1.5 day | No |
| ☐ | `t33_eval_fixtures_and_personas.md` Eval fixtures and personas | 0.75 day | Yes |
| ☐ | `t34_eval_suite_and_baseline.md` Eval suite, metrics and baseline | 1.75 day | Yes |
| ☐ | `t35_hardening_and_documentation.md` Hardening and documentation | 1 day | No |

## Checkpoints

- **After T12** — the entire planning-state system works and is tested, with zero model calls and zero cost. If anything here is shaky, stop and fix it; every later bug will otherwise look like an agent bug.
- **After T22** — orchestration, permissions and guardrails are live and tested against stubs, before a single agent prompt exists.
- **After T25** — first real demo: a one-line requirement in, an understanding and a smart question batch out, coverage meter moving.
- **After T34** — you can measure whether a prompt change made things better. Before this point you are tuning by vibes.

## Open decisions (from DESIGN.md §6.7)

| # | Question | Blocks | Resolve by |
|---|---|---|---|
| 1 | ~~Do Coditas templates exist?~~ | — | **Resolved 2026-09-23: no. T04 defines our own.** |
| 2 | Which model tier for eval runs? | T34 | When you see T34 runtimes — T01 wired a `cheap` tier, flip `PPA_MODEL_TIER` |
| 3 | ~~Is web search available on subscription auth?~~ | — | **Resolved 2026-09-23: yes. T28/T29 ship with research, not degraded.** |
