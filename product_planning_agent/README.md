# Product Planning Agent

An agent that takes a rough requirement, interrogates it with sharp questions, and builds a
versioned, auditable planning ledger you can actually hand to a team.

The design lives in `../Plan/Design and Build plan.md`. The build order lives in `../tasks/`.

## Status

**All 35 build tasks complete** (`tasks/readme.md`'s own board). Discovery — intake, clarify,
change, review and guidance/research modes — runs end to end against the readiness gate; the
ledger is event-sourced, audited and crash-safe; `tests/eval/` carries a live-model eval suite
with a recorded baseline. `ppa report` is the one command still a stub (`grep -rn "is not built
yet" ppa/cli.py` — it never made it onto the board as its own task; everything the seven real
commands below cover is built and tested).

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

## The seven commands

`doctor` (environment/model wiring, shown above) sits outside this list — these seven are what
you actually run against a project, in the order a project usually meets them:

| Command | What it does |
|---|---|
| `ppa new <name> --seed-requirement "..."` | Starts a project: its own local git repo, one rough requirement, the ledger-contents notice. |
| `ppa chat <project>` | The main loop — runs Discovery turns, asks you whatever it needs to, until a round suspends on a question, completes, or escalates. |
| `ppa status <project>` | The one status surface: coverage, readiness, ledger counts. `--items` narrows it to just the open-items list; `--cost` swaps it for the token/cost breakdown per agent and per mode. |
| `ppa history <project> <id>` | Every recorded change to one entity, oldest first. |
| `ppa why <project> <id>` | Explains a decision from the ledger alone — what was chosen and why, plus *which agent, with which tool, in which workflow state* touched it (folded from `audit.ndjson`). |
| `ppa force-ready <project> --reason "..."` | Overrides the readiness gate. Records every blocker that was skipped, and why. |
| `ppa client-questions <project>` | Renders every externally-owned open item as a sendable client questionnaire. |

## Worked example

Start a project. The ledger-contents notice (§2.19.1) prints every time:

```
$ ppa new "Invoice Automation" --seed-requirement "freelancers need to send clients a branded invoice from the app"
Created project invoice-automation at projects\invoice-automation

the ledger stores your requirements and answers verbatim, including client
information; it is a local git repo; add a remote only if that is appropriate
for this project
```

Run `ppa chat invoice-automation` and discovery starts asking. Each pending question renders as a
card — this one's real output, not the model's prose, from `render_question_card`:

```
How many freelancers will use this at launch — a handful, or hundreds?
  why: determines whether invoice generation needs to be async/queued or can run inline
  options: Under 20, 20-200, 200+
  default: Under 20 (most Coditas client pilots start small)
  (you can also say: I don't know / decide later / not relevant)
>
```

Type a real answer, `I don't know`, `decide later`, or `not relevant: <reason>` — `chat` keeps
asking and recording until a round has nothing left pending, then prints the status board. A few
rounds in, suppose discovery has confirmed one requirement, opened one decision and recorded one
client-owned unknown:

```
$ ppa status invoice-automation
PLANNING STATUS — Invoice Automation              Session 2 · 2026-10-01 05:43

Coverage  1/9 critical █░░░░░░░░░░░   all areas 2/12   Round 0 · INTAKE

  critical  ✓ scope_in
            ○ problem (UNTOUCHED)
            ○ users (UNTOUCHED)
            ○ scope_out (UNTOUCHED)
            ○ constraints (UNTOUCHED)
            ○ existing_system (UNTOUCHED)
            ○ platform (UNTOUCHED)
            ○ data (UNTOUCHED)
            ○ nfr (UNTOUCHED)
  other     ✓ jobs ○ success ○ rollout

Ledger
  Requirements    1   (1 confirmed)
  Assumptions     0   (0 confirmed · 0 awaiting review)
  Decisions       1   (0 decided · 0 decide-later · 1 open)
  Unknowns        1   (1 blocking · 0 research)

Readiness   NOT READY — 17 blockers
  🔴  critical area 'constraints' is UNTOUCHED — needs a CONFIRMED requirem…
  🔴  critical area 'data' is UNTOUCHED — needs a CONFIRMED requirement cov…
  ...(6 more critical areas, same shape)...
  🔴  no Requirement covers critical area 'constraints' yet
  ...(7 more, same shape)...
  🔴  the user has not yet approved the REVIEW summary

Open items due within 3 days: 1      Overdue: 0
```

`--items` narrows to just readiness plus the full open-items list (owner and due date included —
"owner: you" for yours, "owner: client" for the ones you'd send out via `client-questions`):

```
$ ppa status invoice-automation --items
...
Open items
  ⚠  DEC-001  Which PDF rendering lib…  owner: you  due Oct 2
  🔴  UNK-001  Does the client's brand…  owner: client
```

`--cost` is the token/cost instrumentation (S13.3) — per turn, per agent, per mode, folded from
`turn.cost_recorded` events, never a live estimate:

```
$ ppa status invoice-automation --cost
COST — Invoice Automation

Total       2 turns · $0.0699 · ~4000 tokens

By agent:
  discovery        2 turns · $0.0699 · ~4000 tokens

By mode:
  clarify          1 turns · $0.0287 · ~1860 tokens
  intake           1 turns · $0.0412 · ~2140 tokens
```

`why` answers "what did we decide and why" *and* "who touched this, with what, under which
workflow state" — the second half is `ppa why`'s own provenance box, folded straight from
`audit.ndjson`:

```
$ ppa why invoice-automation DEC-001
# DEC-001: Which PDF rendering library should invoices use?

**Status:** OPEN

**Provenance (agent · tool · workflow state):**
- 2026-10-01 05:43 · discovery used `manage_decision` (write) in DISCOVERY — ok — needs a technical choice before build
```

`client-questions` turns every externally-owned open item into something you can paste into an
email:

```
$ ppa client-questions invoice-automation
# Coditas Default — Questions for you

## In scope

### Does the client's brand book require a specific invoice layout?
- **Why it matters:** affects the PDF template's structure
- **What we'll assume until you confirm:** not yet recorded
- **Blocking:** Yes
```

And if you need to ship before every blocker clears, `force-ready` overrides the gate — but never
silently:

```
$ ppa force-ready invoice-automation --reason "shipping a thin slice, rest tracked outside the ledger"
Readiness gate overridden. shipping a thin slice, rest tracked outside the ledger
```

Come back to the same project a week later — `ppa chat invoice-automation` again, or any of the
read commands above — and you get the exact same picture: `ppa.ledger.digest.read_digest` rebuilds
everything fresh from `events.ndjson` on every call, with "due soon" always computed against *today*,
never against how old the ledger's own timestamps are (see Crash recovery and resumption, below).

## Crash recovery and resumption

**A killed session needs no manual repair.** `ppa.ledger.materialize.current_entities` excludes any
transaction (`txn_id`) whose matching `txn.commit` never arrived — the log is append-only, so a
crash mid-turn leaves orphaned lines on disk, but they are already invisible to every reader of
ledger state. The next `ppa chat <project>` (or any other command) just opens the project and reads
the ledger fresh; there is no separate recovery command to remember to run.

**Nothing here depends on wall-clock age.** `open_project` reads only `project.json` and
`events.ndjson`; `read_digest` rebuilds the full digest from the event log on every call, never from
a cached or previously materialized snapshot. A project untouched for a week resumes with exactly as
much context as one from five minutes ago — the only thing that changes is that date-relative
numbers ("due within 3 days") are computed against the real current moment, not against how old the
project's own events are.

## A word about what the ledger holds

Once projects exist, the ledger stores your requirements **and your answers verbatim**, including
any client information you type in. It is a local git repo. `create_project` configures no remote,
and `projects/` is gitignored here — add a remote only if that is appropriate for the project.

Obvious credential shapes are detected and redacted *before* anything is written, because the event
log is append-only and there is no unwriting. That is a safety net, not a licence: describe an
integration rather than pasting a connection string.

## Single-writer assumption

`ppa/ledger/store.py::append_event` locks around the read-counter/write-line/fsync sequence with an
**in-process `threading.Lock`**, not an OS-level file lock. That is enough to make concurrent
appends from multiple threads in the same process safe — no interleaved lines, no event id handed
out twice — and it matches how this tool is actually run: one CLI process per project, one writer.

**It does not protect against two separate OS processes appending to `events.ndjson` at the same
time.** If you ever run two `ppa` processes against the same project concurrently, their writes can
interleave or clobber each other's event ids. Don't do that. A future need for genuine multi-process
writers would mean adding a real cross-process lock (`msvcrt.locking` on Windows, `fcntl.flock` on
POSIX) — nothing here provides one today.

## Layout

| Path | What lives there |
|---|---|
| `ppa/orchestrator/` | Outer loop, dispatch, preconditions, escalation |
| `ppa/agents/` | Agent protocol, Discovery, and the Guidance/Research subagents |
| `ppa/tools/` | ToolSpec contract, registry, permission gate, the tools themselves |
| `ppa/validation/` | The five validation layers, permission first |
| `ppa/engines/` | Coverage, readiness, impact, dates, conflicts |
| `ppa/ledger/` | Events, entities, audit, secret scanning, materializer, digest |
| `ppa/recovery/` | Transaction checkpoint/rollback verification, local retry |
| `ppa/workflow/` | The workflow state machine and its legal transitions |
| `ppa/render/` | Status board, question cards, `ppa why`, client questionnaire |
| `ppa/results/` | Error categories and the shared result envelope |
| `ppa/providers/` | `ModelProvider` and `ResearchProvider` — the only seams that know about models and credentials |
| `config/` | Model tier, house style, templates |
| `docs/decisions/` | Decisions with dates and evidence |
| `tests/eval/` | The live-model eval suite, rubric, scorecard and recorded baseline |
