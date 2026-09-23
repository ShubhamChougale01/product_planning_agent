# Blockers

A running log of anything that stopped, slowed or misdirected work on the build board.
One row per issue, added when it happens, not reconstructed later.

**Scope:** things that actually occurred. Risks that have not yet bitten live in the
watchlist at the bottom, deliberately kept out of the table so the table stays honest.

---

## Log

| No | Blockers | Description | Date (When it occured) | Timestamp (when it occured) | Feedback | Suggestion to fix | Task_file_name |
|---|---|---|---|---|---|---|---|
| 1 | Done-when gate was unsatisfiable as written | The final acceptance box required `grep -ri 'sk-ant\|api_key' .` to return nothing outside `.gitignore`. Impossible to satisfy: `api_key` legitimately appears as the *name* of an environment variable (`api_key_env: "ANTHROPIC_API_KEY"` in `ModelConfig`, and the matching key in `config/model.yaml`). Satisfying it literally would mean obfuscating env var names, making the code worse. | 2026-09-23 | 14:28 IST (during T01 verification, ~6 min before the T01 commit) | Not a true blocker — work continued. But it is a task-file defect, and DESIGN.md §2.19.1 is clearly about credential **values** never being written down, not about the identifier being unmentionable. | Amended the box in the task file before moving it to `completed_tasks/`, per the board's own rule. Replaced the literal grep with the real intent, now enforced as tests in `tests/test_secrets/test_repo_hygiene.py`: no `sk-ant-…` literal, and no 16+ char literal assigned to anything named key/token/secret/password. Both clean. **Resolved.** | `t01_environment_and_model_seam.md` |
| 2 | Module naming mismatch between task files | T01's scaffold step points at DESIGN.md §2.6, which only specifies the directory `ppa/ledger/`. The entity module was therefore created as `ppa/ledger/entities.py`. T02 names the file explicitly as `ppa/ledger/models.py`. The T01 handoff note then pointed the next task at the wrong path. | 2026-09-23 | 15:17 IST (found while checking T02 prerequisites, after T01 was already committed) | Caught before T02 started, so it cost nothing. Would have been two minutes of confusion at the top of T02 had it slipped through. Root cause is that §2.6 lists directories but not every filename, so scaffolding has to guess. | Renamed `entities.py` → `models.py` (`git mv`, stub docstring updated), corrected the T01 handoff note, re-ran the suite (16 passed). Committed as `8c2166d`. **Resolved.** For later tasks: when §2.6 is silent on a filename, check whether a downstream task names it before inventing one. | `t01_environment_and_model_seam.md` → `t02_domain_entities_and_status_model.md` |

**Timestamps** are local machine time (IST). Where the exact moment of discovery was not
recorded, the time is anchored to the commit that fixed it and marked as such.

---

## Watchlist — risks that have not occurred yet

These are not blockers. They are the things most likely to become row 3.

| Risk | Bites at | Why it is not a blocker today | Early warning to watch for |
|---|---|---|---|
| **Subscription rate limits** | T23–T34, worst at T34 | The zero-cost path is verified and working. But subscription usage limits are a different constraint from API credits, and nothing in the plan accounts for them. T34 runs an eval suite repeatedly. | Model calls starting to fail or throttle during Phase D. Mitigation is already in place: flip `PPA_MODEL_TIER=cheap` (Haiku 4.5) or switch `auth_source` to `api_key` — one config line either way, by design. |
| **Open decision #2 — eval model tier** | T34 | Deliberately deferred until T34 runtimes are visible. The `cheap` tier was pre-wired in T01 for exactly this. | Nothing to watch. Resolve it by measuring, not by guessing. |
| **The task chain is almost entirely serial** | T13 onward | T02 fans out to T03/T04/T05, and T10–T12 can run in parallel after T07. But T13→T14→…→T35 is a single line, each task gated on the one before it. | A schedule risk, not a correctness one. Only matters if you want to parallelise the work or bring someone else in. |

---

## How to use this file

Add a row the moment something blocks or misdirects you — before fixing it, while the detail
is still exact. A blocker discovered and fixed in the same ten minutes is still worth a row:
the pattern across rows is the useful part, not any single entry.

If a task file turns out to be wrong, the board's rule applies — **edit the task file before
moving it to `completed_tasks/`** — and record the amendment here as well, so the reason
survives alongside the change.
