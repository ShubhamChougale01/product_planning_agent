# Product Planning Agent

An agent that takes a rough requirement, interrogates it with sharp questions, and builds a
versioned, auditable planning ledger you can actually hand to a team.

The design lives in `../Plan/Design and Build plan.md`. The build order lives in `../tasks/`.

## Status

**T01 complete.** Scaffold, dependencies and the model seam are in place. Everything else is a
stub that names the task which fills it — `grep -rn "Not implemented yet" ppa/` is an honest
picture of what is left.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

You also need to be logged into Claude Code (`claude login`). The Agent SDK spawns the CLI and
inherits that login, so **no API key is required**. Verified 2026-09-23 — see
`docs/decisions/auth.md`, and re-run `scripts/verify_auth.py` if you want to check it yourself.

## Usage

```bash
.venv/Scripts/python.exe -m ppa.cli --help     # what exists
.venv/Scripts/python.exe -m ppa.cli doctor     # model and auth wiring
.venv/Scripts/python.exe -m pytest              # the suite
```

## A word about what the ledger holds

Once projects exist, the ledger stores your requirements **and your answers verbatim**, including
any client information you type in. It is a local git repo. `create_project` configures no remote,
and `projects/` is gitignored here — add a remote only if that is appropriate for the project.

Obvious credential shapes are detected and redacted *before* anything is written, because the event
log is append-only and there is no unwriting. That is a safety net, not a licence: describe an
integration rather than pasting a connection string.

## Layout

| Path | What lives there |
|---|---|
| `ppa/orchestrator/` | Outer loop, dispatch, preconditions, escalation |
| `ppa/agents/` | Agent protocol, Discovery, and the Guidance/Research subagents |
| `ppa/tools/` | ToolSpec contract, registry, permission gate, the tools themselves |
| `ppa/validation/` | The five validation layers, permission first |
| `ppa/engines/` | Coverage, readiness, impact, dates, conflicts |
| `ppa/ledger/` | Events, entities, audit, secret scanning, materializer, digest |
| `ppa/providers/` | `ModelProvider` and `ResearchProvider` — the only seams that know about models and credentials |
| `config/` | Model tier, house style, templates |
| `docs/decisions/` | Decisions with dates and evidence |
