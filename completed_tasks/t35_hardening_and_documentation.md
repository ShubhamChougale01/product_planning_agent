# T35 — Hardening and documentation

| | |
|---|---|
| **Phase** | F · Resilience and validation |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.16, §6.6, S13.1–S13.5 |

## Prerequisites

- [x] **T34**

## Why this task exists

The last mile: surviving restarts, resuming a week later, and being explainable to someone who
was not in the conversation. `ppa why` is the traceability payoff the whole event-sourced ledger
was built for.

## What to build

### Crash recovery
Resume from the last committed transaction. An interrupted session must not require manual repair.

### Session resumption
`ppa chat <project>` days later restores full context from the digest. **Test with a week-old
fixture**, not a fresh one.

### Cost instrumentation
Tokens per turn, per agent, per mode. Find the expensive mode before it matters.

### `ppa why <id>`
Walk events **and audit** to explain provenance: what changed, when, why, by which agent, under
which tool, in which workflow state. This is what the two-log design (T08) bought.

### Documentation
- README: the seven commands, one worked example end to end
- **The single-writer constraint, stated explicitly** (§6.6) — so it is not discovered accidentally
- **The ledger-contents notice** (§2.19.1) — verbatim answers, local git repo, add a remote only
  if appropriate
- `docs/decisions/` — the three open decisions from §6.7, with their resolutions

## Files touched

```
README.md
docs/decisions/*.md
ppa/cli.py  (extend)
tests/test_recovery/test_resume.py
```

**Actually touched** (wider than the list above, for reasons the Build record explains):
`ppa/ledger/events.py` (new `EventType.TURN_COST_RECORDED`); `ppa/orchestrator/loop.py` (new
`_write_turn_cost_event`, called once per `run_turn`); `ppa/render/status_board.py` (new
`render_cost_report`/`_cost_rows`); `ppa/cli.py` (new `--cost` flag on `status`, not a new
command); `tests/test_agents/test_loop.py`, `tests/test_render/test_status_board.py`,
`tests/test_render/test_cli.py` (cost-instrumentation coverage); `docs/decisions/
house_style_templates.md` (new — the one §6.7 decision that had no doc file yet);
`tasks/readme.md` (§6.7 table row 1 now points at it; T35 ticked on the board).

## Done when

- [x] A killed session resumes with no manual repair
- [x] A week-old project resumes with full context from the digest
- [x] `ppa why <id>` reports agent, tool and workflow state, not just the change
- [x] Token cost is broken down per agent and per mode
- [x] README documents all seven commands with one worked example
- [x] The single-writer constraint is stated explicitly in the README
- [x] The ledger-contents notice is in the README and shown on `ppa new`
- [x] All three open decisions from §6.7 are resolved and recorded

## Build record

**Three of the four build items were already done — this task's real job was proving it, not
building it.** `ppa.ledger.materialize.current_entities` has excluded any `txn_id` with no
matching `txn.commit` since T07, and T32 already proved that rollback guarantee directly
(`ppa/recovery/transaction.py`, `tests/test_recovery/test_transaction.py`). `ppa.ledger.project.
open_project` and `ppa.ledger.digest.read_digest` both rebuild everything fresh from
`project.json`/`events.ndjson` on every call — no cache, no dependency on wall-clock age anywhere
in the read path. And `ppa why <id>` already existed, built across T28 (`render_why`, decision
provenance from ledger content) and T31 (`render_provenance`, the agent/tool/workflow-state half
folded from `audit.ndjson`) — both already covered by `tests/test_render/test_status_board.py`
and `tests/test_render/test_cli.py` before this session started.

So the actual new work for those three was `tests/test_recovery/test_resume.py`: one test proving
resumption from the CLI's own entry point (`open_project` + `loop.run_turn` again, after an
orphaned, never-committed `DECISION_OPENED` event simulates a kill mid-turn — no recovery step
runs, the next turn just proceeds and the orphaned decision stays invisible), and one proving a
week-old project's digest is anchored to the real current moment: a `Decision` opened and
timestamped a week in the past, with `expected_decision_date` set two days out from *today* (not
from back then), appears under "Due within 3 days" when read with today's `now` — and does **not**
appear under that heading when the same digest is read with `now` set back to the week-old
timestamp, proving the date math genuinely re-anchors rather than just always showing everything.

**Cost instrumentation was the one genuinely new feature.** `ppa/agents/turn.py` already captured
`cost_usd` per turn (from `ResultMessage.total_cost_usd`, T34's own fix to route every real model
call through `ModelProvider.from_config`) and `ppa/orchestrator/loop.py` already computed
`bundle.token_estimate` per turn — `loop.py:539`'s own comment named T35 as the task that would
use it. Neither number was ever persisted past the turn that produced it. Fixed with one new event
type, `turn.cost_recorded` (`entity_id=None`, same pattern as `TXN_COMMIT`/
`ANOMALY_LOOP_CAP_REACHED` — observability about the turn, never replayed into entity state),
written once per `run_turn` call via a new `_write_turn_cost_event` helper. `mode` falls back to
the agent's own id for the subagents (guidance/research) that never populate `result.data["mode"]`
the way the discovery turn does; `cost_usd` is `None` for stub/fixture agents in tests, same as a
turn with no real model call behind it.

Surfaced as `ppa status --cost` — a flag on the existing `status` command, not an eighth command,
matching the "one surface" principle `render_status_board`'s own module docstring already states
and keeping the README's "seven commands" count accurate (`--items` set the precedent). `doctor`
sits outside that count on purpose — it is environment/model-wiring diagnostics, not something run
against a project; the seven are `new`, `chat`, `status`, `history`, `why`, `force-ready`,
`client-questions`. `report` (`ppa/cli.py`'s own `_not_yet` stub) was never scheduled as its own
task anywhere on the board and stays a stub — out of scope here, called out honestly in the
README's Status section instead of silently ignored.

**The worked example is real captured output, not invented text.** A throwaway script (not
committed — it lived in the job's own scratch directory) ran the actual CLI (`typer.testing.
CliRunner`) against a project seeded with one confirmed `Requirement`, one open `Decision` (with a
real `record_audit` call behind it, so `ppa why`'s provenance box has something genuine to show),
and one blocking `Unknown`, plus two `turn.cost_recorded` events — then captured real stdout for
`new`, `status` (plain/`--items`/`--cost`), `history`, `why`, `client-questions` and `force-ready`,
ANSI codes stripped. The one command that couldn't be captured this way is `chat` itself (it is
genuinely interactive and its real turns need a model) — the question-card excerpt in the README
is `render_question_card`'s own real output against a sample question dict, not a live transcript,
and the README says so.

**`docs/decisions/`:** two of the three §6.7 decisions already had dedicated files
(`model_tier.md` from T34, `auth.md` from T01) — `tasks/readme.md`'s own table already linked to
`model_tier.md`; `auth.md` answers the "is web search available" question (#3) even though the
table didn't link it by name. Decision #1 (Coditas templates — resolved 2026-09-23 as "no, T04
defines our own") had no file of its own, only an inline note in the table; added
`docs/decisions/house_style_templates.md` for consistency with the other two, and pointed the
table's row 1 at it.

**Full suite re-confirmed clean after every change in this session:** 909 tests (902 at session
start + 7 new: two in `test_loop.py`, two in `test_status_board.py`, one in `test_cli.py`, two in
`test_resume.py`), 0 failures, 0 errors, 1 skipped, exit 0.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/`
3. Commit: `git add -A && git commit -m "T35: Hardening and documentation"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t35_*.md completed_tasks\
   bash:     mv tasks/t35_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T35` on the board.
