# T01 — Environment, scaffold and the model seam

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.5 day |
| **Needs a model?** | One 10-line script |
| **Design reference** | DESIGN.md §0.1, §2.6, S0.1–S0.3 |

## Prerequisites

_None — this task can start immediately._

## Why this task exists

Everything else assumes two things that have not been proven: that the Claude Agent SDK runs on
your Claude Code subscription without API credits, and that web search is reachable on that auth
path. Both are cheap to check and expensive to discover later. The second one decides whether
Guidance Mode ships with research or degraded (T29), so answer it now.

## What to build

### 1. Verify subscription auth

Install `claude-agent-sdk`. Log into Claude Code (`claude login`). Write a 10-line script that
calls `query()` once and prints the reply. Run it with `ANTHROPIC_API_KEY` **unset**.

Record the answer in `docs/decisions/auth.md` — yes or no, with the date and SDK version. If it
is no, the plan still holds but the budget does not; flag it before continuing.

### 2. Verify web search on that path

In the same session, ask the model something that requires a current web lookup and see whether a
search tool is available. Record it in the same file. This resolves open decision #3.

### 3. Scaffold

Create the package layout from DESIGN.md §2.6. Empty `__init__.py` files are fine; the point is
that imports resolve and `pytest` runs. Add `pyproject.toml` with: `pydantic`, `typer`, `rich`,
`claude-agent-sdk`, `pyyaml`, `pytest`, `pytest-cov`, `freezegun`.

### 4. The ModelProvider seam

`ppa/providers/model.py` — a single class that decides model id and auth source, reading from
config with env override. Nothing else in the codebase may name a model string or read an API key.

```python
class ModelProvider:
    def __init__(self, cfg: ModelConfig): ...
    def client(self) -> ClaudeSDKClient: ...
```

Credentials come from environment or OS keychain **at call time**. Never written to disk, never
placed in a prompt, never logged (§2.19.1).

## Files touched

```
product_planning_agent/
├── pyproject.toml
├── .gitignore
├── docs/decisions/auth.md
├── ppa/__init__.py  ppa/providers/model.py
└── tests/__init__.py
```

## Done when

- [x] `python -m ppa.cli --help` prints without error
- [x] `pytest` runs green on zero tests
- [x] The auth question is answered in writing, with a date
- [x] The web-search question is answered in writing
- [x] Switching model is a config change — `grep` finds no model string outside `providers/model.py`
- [x] ~~`grep -ri 'sk-ant\|api_key' .` returns nothing outside `.gitignore`~~ **Amended, see below** —
      no credential *value* exists anywhere in the repo

### Amendment to the last box (2026-09-23)

As written this box is unsatisfiable, and satisfying it would make the code worse. `api_key`
appears legitimately as the *name* of an environment variable — `api_key_env: "ANTHROPIC_API_KEY"`
in `ModelConfig`, and the config key that points at it. §2.19.1 is about credential **values**
never being written down, not about the identifier being unmentionable.

The check as actually enforced, now in `tests/test_secrets/test_repo_hygiene.py`:

- no `sk-ant-…` literal anywhere
- no 16+ character literal assigned to anything named key/token/secret/password
- env var *names* are allowed, because a credential has to be fetched from somewhere

Both return clean. The grep is a test now rather than a one-off, so it holds for T02–T35.

## Traps

Do not skip step 1 because you are confident. The entire zero-cost plan rests on it, and it
costs ten minutes. If it fails you want to know on day one, not day nine.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/`
3. Commit: `git add -A && git commit -m "T01: Environment, scaffold and the model seam"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t01_*.md completed_tasks\
   bash:     mv tasks/t01_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T01` on the board.

---

## Build record (completed 2026-09-23)

### The two questions this task existed to answer

| Question | Answer | Evidence |
|---|---|---|
| Does the Agent SDK run on Claude Code subscription auth, no API credits? | **Yes** | `query()` returned `AUTH_OK` with `ANTHROPIC_API_KEY` unset |
| Is web search reachable on that path? | **Yes** | tools invoked: `['ToolSearch', 'WebSearch']`, returned a live 2026-09-22 headline with sources |

Written up with versions and re-run instructions in `docs/decisions/auth.md`. The probe itself is
`scripts/verify_auth.py` and is re-runnable.

**Open decision #3 is closed: Guidance Mode (T28) and Research Mode (T29) ship with research from
day one, not degraded.** The `ResearchProvider` degradation path in §6.5 is still worth building —
it covers search being rate-limited, erroring or config-disabled — but it is no longer the default.

**One caveat for T34.** `ResultMessage.total_cost_usd` still reports a figure (~0.17 and ~0.14 USD
for the two probes) even with no API key present. That is equivalent-cost accounting on the
subscription, not a metered charge. Useful as a *relative* signal when sizing eval runs; do not
read it as a bill.

### Decisions taken during the build

| Decision | Choice | Why |
|---|---|---|
| Where the package lives | `product_planning_agent/` nested under the project root | Keeps code separate from `Plan/` and `tasks/`; matches the §2.6 diagram literally |
| Dependencies | project-local `.venv` | Keeps the global Python 3.13 clean, keeps the build reproducible |
| Model configuration | config names a **tier**, not a model id | Satisfies the no-model-strings gate properly: `config/model.yaml` says `tier: primary`, and the tier→id table sits alone in `providers/model.py`. Three tiers: `primary` (Sonnet 5), `deep` (Opus 5), `cheap` (Haiku 4.5) |
| Stub modules | every §2.6 module created with a docstring naming the task that fills it | `grep -rn "Not implemented yet" ppa/` gives an honest picture of remaining work, and imports resolve today |

The `cheap` tier exists specifically for **open decision #2** (which model tier for eval runs) —
T34 can flip `PPA_MODEL_TIER=cheap` and measure, without touching agent logic.

### Extra work beyond the task as written

Tests were added, though the task only asked for pytest to run green on zero tests. Two reasons:
the grep gates are guarantees that must hold for the next 34 tasks, and a seam whose whole job is
"never leak a credential" should have that asserted rather than eyeballed. 16 tests, all passing:

- `tests/test_secrets/test_repo_hygiene.py` — the two grep gates, plus `.gitignore` coverage
- `tests/test_agents/test_model_provider.py` — tier resolution, env-over-file precedence,
  credentials resolved at call time and never stored on the instance or in `describe()`

### What exists now

```
product_planning_agent/
├── .venv/                       # python 3.13.13
├── pyproject.toml  .gitignore  README.md
├── docs/decisions/auth.md       # the two answers, dated
├── scripts/verify_auth.py       # re-runnable probe
├── config/model.yaml  config/house_style.yaml (placeholder, T04)
├── ppa/                         # full §2.6 tree, 52 modules, all importable
│   ├── cli.py                   # doctor works; new/plan/status/report declared, arrive at T31
│   └── providers/model.py       # the seam — the only file naming a model or touching a credential
└── tests/                       # 16 passing
```

### Verification output

```
$ .venv/Scripts/python.exe -m ppa.cli --help   -> prints, 5 commands listed
$ .venv/Scripts/python.exe -m ppa.cli doctor   -> model claude-sonnet-5 / auth subscription / credential claude-code-cli-login
$ .venv/Scripts/python.exe -m pytest           -> 16 passed
$ grep model ids outside the seam   -> clean
$ grep credential values            -> clean
```

### Notes for whoever picks up T02

- Install with `.venv/Scripts/python.exe -m pip install -e ".[dev]"`, run everything through that
  interpreter rather than the global one.
- Entities go in `ppa/ledger/models.py`, which is stubbed and waiting. The seven entity types and
  the shared `id/version/status/created_at/updated_at/created_by/updated_by/history[]` base are in
  DESIGN.md §2.7.
- Do not name a model anywhere. Ask `ModelProvider` for a tier. There is a test that will fail you.
