# Blockers, decisions and bugs

The running record for this build. Three tables, one purpose each:

| Section | What goes in it |
|---|---|
| **1 · Blockers** | Anything that stopped, slowed or misdirected work |
| **2 · Decisions** | Every choice made — taken *and* still pending |
| **3 · Bugs** | Defects found in code we wrote |

Add the row when it happens, not later. A thing found and fixed in the same ten minutes still
gets a row — the pattern across rows is the useful part, not any single entry.

**Scope rule:** these tables hold things that actually happened or were actually decided. Risks
that have not yet bitten live in the watchlist at the bottom, kept separate so the tables stay
honest.

---

## 1 · Blockers

| No | Blockers | Description | Date (When it occured) | Timestamp (when it occured) | Status | Feedback | Suggestion to fix | Task_file_name |
|---|---|---|---|---|---|---|---|---|
| 1 | Done-when gate was unsatisfiable as written | The final acceptance box required `grep -ri 'sk-ant\|api_key' .` to return nothing outside `.gitignore`. Impossible to satisfy: `api_key` legitimately appears as the *name* of an environment variable (`api_key_env: "ANTHROPIC_API_KEY"` in `ModelConfig`, and the matching key in `config/model.yaml`). Satisfying it literally would mean obfuscating env var names, making the code worse. | 2026-09-23 | 14:28 IST (during T01 verification, ~6 min before the T01 commit) | **Resolved** | Not a true blocker — work continued. But it is a task-file defect, and DESIGN.md §2.19.1 is clearly about credential **values** never being written down, not about the identifier being unmentionable. | Amended the box in the task file before moving it to `completed_tasks/`, per the board's own rule. Replaced the literal grep with the real intent, now enforced as tests in `tests/test_secrets/test_repo_hygiene.py`: no `sk-ant-…` literal, and no 16+ char literal assigned to anything named key/token/secret/password. Both clean. | `t01_environment_and_model_seam.md` |
| 2 | Module naming mismatch between task files | T01's scaffold step points at DESIGN.md §2.6, which only specifies the directory `ppa/ledger/`. The entity module was therefore created as `ppa/ledger/entities.py`. T02 names the file explicitly as `ppa/ledger/models.py`. The T01 handoff note then pointed the next task at the wrong path. | 2026-09-23 | 15:17 IST (found while checking T02 prerequisites, after T01 was already committed) | **Resolved** | Caught before T02 started, so it cost nothing. Would have been two minutes of confusion at the top of T02 had it slipped through. Root cause is that §2.6 lists directories but not every filename, so scaffolding has to guess. | Renamed `entities.py` → `models.py` (`git mv`, stub docstring updated), corrected the T01 handoff note, re-ran the suite (16 passed). Committed as `8c2166d`. For later tasks: when §2.6 is silent on a filename, check whether a downstream task names it before inventing one. | `t01_environment_and_model_seam.md` → `t02_domain_entities_and_status_model.md` |

**Timestamps** are local machine time (IST). Where the exact moment of discovery was not
recorded, the time is anchored to the commit that fixed it and marked as such.

---

## 2 · Decisions

Both taken and pending. A pending decision with no row here is a decision that will get made by
accident.

| No | Decision | Description | Date (When it occured) | Timestamp (when it occured) | Status | Feedback | Consequence / follow-up | Task_file_name |
|---|---|---|---|---|---|---|---|---|
| 1 | **Repo is public, and everything was pushed knowingly** | Pushed all 117 tracked files to `github.com/ShubhamChougale01/product_planning_agent` on `main`. Visibility could not be verified from the shell (`gh` not installed), so it was raised before pushing and confirmed as public with everything included. | 2026-09-23 | 15:35 IST | **Taken** | Verified before pushing: no `.venv`, no `.env`, no `projects/`, no `*.local.*`, and no credential values in any tracked file. The `ANTHROPIC_API_KEY` strings a naive grep finds are env-var *names*, which is exactly the distinction `tests/test_secrets/test_repo_hygiene.py` enforces. | **`Plan/CLAUDE.md` is now publicly indexable**, including the "about me" section and working preferences. Reversing this needs a history rewrite plus force-push, not a delete — the cost only grows as commits accumulate. `projects/` stays gitignored, so future ledgers holding verbatim client answers never leave the machine; **keep that exclusion**. | — (repo-level) |
| 2 | **Config names a model tier, not a model id** | `config/model.yaml` says `tier: primary`; the tier→id table lives alone in `ppa/providers/model.py`. Three tiers: `primary` (Sonnet 5), `deep` (Opus 5), `cheap` (Haiku 4.5). | 2026-09-23 | 14:20 IST | **Taken** | T01's "no model string outside `providers/model.py`" gate is hollow if the id just moves into YAML. Naming a tier satisfies the intent rather than the letter. | Nothing may name a model anywhere else — there is a test that fails you. The `cheap` tier exists specifically to resolve decision #4 below. | `t01_environment_and_model_seam.md` |
| 3 | **Package nested in `product_planning_agent/`, deps in a project-local `.venv`** | Code sits under `product_planning_agent/` beside `Plan/`, `tasks/` and `completed_tasks/`, matching the §2.6 diagram literally. Dependencies install into `.venv` there. | 2026-09-23 | 14:05 IST | **Taken** | User choice, offered as an explicit option at the start of T01. | Run everything through `.venv/Scripts/python.exe`, not the global interpreter. `.venv/` is gitignored. | `t01_environment_and_model_seam.md` |
| 4 | **Which model tier for eval runs** (DESIGN.md §6.7 open decision #2) | Whether T34's eval suite runs on `cheap`, `primary` or `deep`. Deliberately deferred until real T34 runtimes are visible. | — | — | **PENDING — resolve at T34** | Do not guess this. The whole point of T34 is being able to measure whether a prompt change helped; picking a tier by intuition undermines that. | The `cheap` tier was pre-wired in T01, so resolving it is `PPA_MODEL_TIER=cheap` plus a measurement — no redesign. Tick DESIGN.md §6.7 and the board's open-decisions table when settled. | `t34_eval_suite_and_baseline.md` |
| 5 | **Web search availability on subscription auth** (open decision #3) | Whether Guidance and Research modes ship with live research or degraded. | 2026-09-23 | 14:30 IST | **Resolved — YES** | Probed directly rather than assumed: tools invoked were `['ToolSearch', 'WebSearch']`, returning a live 2026-09-22 headline with sources. Written up in `product_planning_agent/docs/decisions/auth.md`. | T28 and T29 ship **with** research, not degraded. The `ResearchProvider` degradation path is still worth building — it covers search being rate-limited, erroring or config-disabled — but it is no longer the default. | `t01_environment_and_model_seam.md` |
| 6 | **Do Coditas requirement templates exist?** (open decision #1) | Whether to adopt existing house templates or define our own. | 2026-09-23 | — (resolved on the board before T01 began) | **Resolved — NO** | Recorded in `tasks/readme.md`. | T04 defines our own templates and house style. | `t04_config_areas_profiles_house_style.md` |
| 7 | **Status enum for `QuestionAnswer` and `ResearchFinding` — a real gap in DESIGN.md §2.7** | §2.7 gives an explicit status enum for five of the seven entities (Requirement, Assumption, Decision, Unknown, Risk) but not for `QuestionAnswer` or `ResearchFinding`, even though the shared base line requires every entity to carry `status`. Filled the gap by assumption so the schema could be built: `QuestionAnswer` → `PENDING\|ANSWERED\|SUPERSEDED` (mirrors ask→answer→superseded-by-a-later-round); `ResearchFinding` → `ACTIVE\|SUPERSEDED` (staleness is already tracked separately via `stale_after_days` + `researched_at`, computed by engines in T10–T12, so status only needs to track supersession). | 2026-09-23 | 15:30 IST | **Taken (needs confirmation)** — not truly resolved, an assumption filling a spec gap, flagged rather than buried in a docstring | Neither enum is testable against DESIGN.md because DESIGN.md doesn't specify one. Both are exercised in `tests/test_ledger/test_transitions.py` under the chosen names, so a rename is mechanical, not a redesign. | **Developer: please confirm or override these two enums.** If changed, update `TRANSITIONS` in `ppa/ledger/transitions.py` to match — nothing downstream depends on the specific values yet, but T09 (digest) and T25 (question engine) will start reading `QuestionAnswer.status` soon. | `t02_domain_entities_and_status_model.md` |
| 8 | **Same-status transitions (`frm == to`) are legal for every entity type** | Not stated in DESIGN.md. Re-saving an entity without changing its status is not a status change, and treating it as illegal would penalize idempotent writes for no reason — §1.15 names idempotency as a requirement elsewhere in the design, just not for this specific case. | 2026-09-23 | 15:30 IST | **Taken** | Minor, but worth recording since it's a rule `validate_transition()` enforces that no task file asked for explicitly. | Tested in `tests/test_ledger/test_transitions.py::test_same_status_transition_is_always_legal`. Revisit only if a future task needs "no-op writes must also be explicit events" — nothing currently does. | `t02_domain_entities_and_status_model.md` |

---

## 3 · Bugs

Defects in code we wrote — as distinct from a task file being wrong (that is a blocker) or a
choice being open (that is a decision).

| No | Bug | Description | Date (When it occured) | Timestamp (when it occured) | Status | Feedback | Suggestion to fix | Task_file_name |
|---|---|---|---|---|---|---|---|---|
| — | _None yet._ | T01 and T02 shipped with no known defects — 116 tests passing (T01's 16 + T02's 100), all green on first run. First stateful logic (writes, events, idempotency) arrives at T03/T06/T07; expect this table to start filling once entities are actually mutated rather than just validated. | — | — | — | — | — | — |

---

## Watchlist — risks that have not occurred yet

Not blockers. The things most likely to become row 3 of section 1.

| Risk | Bites at | Why it is not a blocker today | Early warning to watch for |
|---|---|---|---|
| **Subscription rate limits** | T23–T34, worst at T34 | The zero-cost path is verified and working. But subscription usage limits are a different constraint from API credits, and nothing in the plan accounts for them. T34 runs an eval suite repeatedly. | Model calls starting to fail or throttle during Phase D. Mitigation is already in place: flip `PPA_MODEL_TIER=cheap` or switch `auth_source` to `api_key` — one config line either way, by design. |
| **`total_cost_usd` is not a bill** | T34 | The SDK reports a cost figure (~$0.17, ~$0.14 on the T01 probes) even with no API key present. That is equivalent-cost accounting on the subscription. | Useful as a *relative* signal when sizing eval runs. Do not budget against it as if it were spend. |
| **The task chain is almost entirely serial** | T13 onward | T02 fans out to T03/T04/T05, and T10–T12 can run in parallel after T07. But T13→T14→…→T35 is a single line, each task gated on the one before it. | A schedule risk, not a correctness one. Only matters if you want to parallelise or bring someone else in. |

---

## How to use this file

**Status column (Blockers and Bugs tables)** — one of three values, always:

| Value | Meaning |
|---|---|
| `Resolved` | Fixed, and the fix is committed |
| `In Progress` | Being worked right now |
| `Pending` | Known, not yet started |

Set it to `In Progress` the moment you start on a row, not after — a row sitting at `Pending`
with no `In Progress` row anywhere is a fair question to ask out loud. The Decisions table (§2)
keeps its own richer status wording (`Taken`, `PENDING — resolve at T34`, `Resolved — YES/NO`)
because a decision's status carries the outcome, not just whether work is done — that distinction
is intentional, not an inconsistency to fix.

**Blockers** — add the row before fixing, while the detail is still exact. If a task file turns
out to be wrong, the board's rule applies: **edit the task file before moving it to
`completed_tasks/`**, and record the amendment here too, so the reason survives alongside the
change.

**Decisions** — add a row for anything chosen *or* deferred. Pending rows carry no date and a
`PENDING` status; fill them in when resolved rather than deleting them, so the reasoning
survives. Anything that closes a DESIGN.md §6.7 open decision gets ticked there and on the board
as well.

**Bugs** — code defects only. Include the failing case, not just the symptom. If a test now
guards it, name the test.
