# Blockers, decisions and bugs

The running record for this build. Four sections:

| Section | What goes in it |
|---|---|
| **1 · Blockers** | Blockers that are still open — resolved ones move to §4 |
| **2 · Decisions** | Decisions not yet fully settled — pending, or taken but flagged for confirmation |
| **3 · Bugs** | Known defects still open — fixed ones move to §4 |
| **4 · Completed / resolved** | The full record of everything that's done — moved here, not left duplicated above |

Add the row when it happens, not later. A thing found and fixed in the same ten minutes still
gets a row in §4 directly — the pattern across rows is the useful part, not any single entry.

**Scope rule:** these tables hold things that actually happened or were actually decided. Risks
that have not yet bitten live in the watchlist near the bottom, kept separate so the tables stay
honest.

**Move-on-completion rule:** once a blocker or bug is resolved, or a decision is fully settled, its
row moves out of §1–§3 and into §4 — the *whole* row, full detail intact, not a copy left behind.
§1–§3 show only what is still open, in progress, or not yet attempted, so those tables are always a
true picture of remaining work at a glance. §4 is the permanent archive of everything closed, in
the order it closed. *(This replaces an earlier version of this file that kept resolved rows in
place above and only indexed them in §4 — that design was superseded on request; §4 now holds the
full record, not a pointer to it.)*

---

## 1 · Blockers

No blockers are currently open. Both blockers logged so far are resolved and have moved to §4.

| No | Blockers | Description | Date (When it occured) | Timestamp (when it occured) | Status | Feedback | Suggestion to fix | Task_file_name |
|---|---|---|---|---|---|---|---|---|
| — | _None open._ | — | — | — | — | — | — | — |

**Timestamps** are local machine time (IST). Where the exact moment of discovery was not
recorded, the time is anchored to the commit that fixed it and marked as such.

---

## 2 · Decisions

Only decisions still pending or not yet confirmed live here. Numbering is not contiguous on
purpose — decisions #1, #2, #3, #5, #6, #7 and #8 are fully settled and have moved to §4; #4
keeps its original number rather than being renumbered, so every cross-reference elsewhere in
this file (and in commit messages already pushed) still points at the right row.

**#4 — Which model tier for eval runs** (DESIGN.md §6.7 open decision #2): **PENDING — resolve at
T34** by running `PPA_MODEL_TIER=cheap|primary|deep` and measuring, not by guessing now — see
`t34_eval_suite_and_baseline.md`. Kept to one line because there's nothing to decide yet: no date,
no timestamp, no runtime data exists until T34 actually runs.

_No decisions currently sit in the table below — #4 above is the only one still open._

| No | Decision | Description | Date (When it occured) | Timestamp (when it occured) | Status | Feedback | Consequence / follow-up | Task_file_name |
|---|---|---|---|---|---|---|---|---|
| — | _None._ | — | — | — | — | — | — | — |

---

## 3 · Bugs

No bugs are currently open. Both bugs logged so far are resolved and have moved to §4.

Defects in code we wrote — as distinct from a task file being wrong (that is a blocker) or a
choice being open (that is a decision).

| No | Bug | Description | Date (When it occured) | Timestamp (when it occured) | Status | Feedback | Suggestion to fix | Task_file_name |
|---|---|---|---|---|---|---|---|---|
| — | _None open._ | — | — | — | — | — | — | — |

---

## 4 · Completed / resolved — full record (chronological)

Every blocker, bug and decision that is actually closed, moved here in full — not indexed, not
duplicated above. Oldest first, so this reads as the story of the build. `Ref` keeps each item's
original number from its source table, for traceability into old commit messages that mention
"decision #2" or "bug #1" by number.

**What's excluded, on purpose:** anything still open. That's decision #4 (which model tier for
eval runs — pending, resolves at T34). It stays in §2 exactly because it's not done; moving it
here would misrepresent that.

| Type | Ref | Item | Description | Date | Timestamp | Status | Feedback | Consequence / suggestion to fix | Task_file_name |
|---|---|---|---|---|---|---|---|---|---|
| Decision | #6 | **Do Coditas requirement templates exist?** (open decision #1) | Whether to adopt existing house templates or define our own. | 2026-09-23 | — (resolved on the board before T01 began) | **Resolved — NO** | Recorded in `tasks/readme.md`. | T04 defines our own templates and house style. | `t04_config_areas_profiles_house_style.md` |
| Decision | #3 | **Package nested in `product_planning_agent/`, deps in a project-local `.venv`** | Code sits under `product_planning_agent/` beside `Plan/`, `tasks/` and `completed_tasks/`, matching the §2.6 diagram literally. Dependencies install into `.venv` there. **Confirmed 2026-09-23 by user feedback, re-verified end to end:** `.venv/` is in `.gitignore` and confirmed untracked by `git ls-files`; `README.md`'s every command already uses `.venv/Scripts/python.exe`, never a bare `python`; `test_gitignore_excludes_env_and_project_ledgers` fails the suite if `.venv/` is ever dropped from `.gitignore`. | 2026-09-23 | 14:05 IST | **Taken** | User choice, offered as an explicit option at the start of T01, reconfirmed as correct on review. Checking it against the repo (not just the sentence) found one cosmetic slip — see bug #2 — but no actual violation. | Run everything through `.venv/Scripts/python.exe`, not the global interpreter. `.venv/` is gitignored, and that's now enforced by a test, not just a note in this row. | `t01_environment_and_model_seam.md` |
| Decision | #2 | **Config names a model tier, not a model id** | `config/model.yaml` says `tier: primary`; the tier→id table lives alone in `ppa/providers/model.py`. Three tiers: `primary` (Sonnet 5), `deep` (Opus 5), `cheap` (Haiku 4.5). **Rule, confirmed 2026-09-23 by user feedback:** tier names may appear anywhere; actual model ids may exist only in `ppa/providers/model.py` — enforced by an automated test, not just convention. | 2026-09-23 | 14:20 IST | **Taken** | T01's "no model string outside `providers/model.py`" gate is hollow if the id just moves into YAML. Naming a tier satisfies the intent rather than the letter. Confirmed correct by the user, who flagged that the test itself needed to actually cover this — see bug #1, which the check surfaced a real gap in. | Nothing may name a model anywhere else — there are now two tests that fail you: `test_model_strings_live_only_in_the_seam` (scans `.py`/`.yaml`/`.yml`/`.toml`/`.json` repo-wide) and `test_shipped_config_names_a_tier_not_a_model_id` (asserts the shipped `config/model.yaml` carries no `model_override`). The `cheap` tier exists specifically to resolve decision #4 (§2). | `t01_environment_and_model_seam.md` |
| Blocker | #1 | Done-when gate was unsatisfiable as written | The final acceptance box required `grep -ri 'sk-ant\|api_key' .` to return nothing outside `.gitignore`. Impossible to satisfy: `api_key` legitimately appears as the *name* of an environment variable (`api_key_env: "ANTHROPIC_API_KEY"` in `ModelConfig`, and the matching key in `config/model.yaml`). Satisfying it literally would mean obfuscating env var names, making the code worse. | 2026-09-23 | 14:28 IST (during T01 verification, ~6 min before the T01 commit) | **Resolved** | Not a true blocker — work continued. But it is a task-file defect, and DESIGN.md §2.19.1 is clearly about credential **values** never being written down, not about the identifier being unmentionable. | Amended the box in the task file before moving it to `completed_tasks/`, per the board's own rule. Replaced the literal grep with the real intent, now enforced as tests in `tests/test_secrets/test_repo_hygiene.py`: no `sk-ant-…` literal, and no 16+ char literal assigned to anything named key/token/secret/password. Both clean. | `t01_environment_and_model_seam.md` |
| Decision | #5 | **Web search availability on subscription auth** (open decision #3) | Whether Guidance and Research modes ship with live research or degraded. | 2026-09-23 | 14:30 IST | **Resolved — YES** | Probed directly rather than assumed: tools invoked were `['ToolSearch', 'WebSearch']`, returning a live 2026-09-22 headline with sources. Written up in `product_planning_agent/docs/decisions/auth.md`. | T28 and T29 ship **with** research, not degraded. The `ResearchProvider` degradation path is still worth building — it covers search being rate-limited, erroring or config-disabled — but it is no longer the default. | `t01_environment_and_model_seam.md` |
| Blocker | #2 | Module naming mismatch between task files | T01's scaffold step points at DESIGN.md §2.6, which only specifies the directory `ppa/ledger/`. The entity module was therefore created as `ppa/ledger/entities.py`. T02 names the file explicitly as `ppa/ledger/models.py`. The T01 handoff note then pointed the next task at the wrong path. | 2026-09-23 | 15:17 IST (found while checking T02 prerequisites, after T01 was already committed) | **Resolved** | Caught before T02 started, so it cost nothing. Would have been two minutes of confusion at the top of T02 had it slipped through. Root cause is that §2.6 lists directories but not every filename, so scaffolding has to guess. | Renamed `entities.py` → `models.py` (`git mv`, stub docstring updated), corrected the T01 handoff note, re-ran the suite (16 passed). Committed as `8c2166d`. For later tasks: when §2.6 is silent on a filename, check whether a downstream task names it before inventing one. | `t01_environment_and_model_seam.md` → `t02_domain_entities_and_status_model.md` |
| Decision | #8 | **Same-status transitions (`frm == to`) are legal for every entity type** | Not stated in DESIGN.md. Re-saving an entity without changing its status is not a status change, and treating it as illegal would penalize idempotent writes for no reason — §1.15 names idempotency as a requirement elsewhere in the design, just not for this specific case. | 2026-09-23 | 15:30 IST | **Taken** | Minor, but worth recording since it's a rule `validate_transition()` enforces that no task file asked for explicitly. | Tested in `tests/test_ledger/test_transitions.py::test_same_status_transition_is_always_legal`. Revisit only if a future task needs "no-op writes must also be explicit events" — nothing currently does. | `t02_domain_entities_and_status_model.md` |
| Decision | #1 | **Repo is public, and everything was pushed knowingly** | Pushed all 117 tracked files to `github.com/ShubhamChougale01/product_planning_agent` on `main`. Visibility could not be verified from the shell (`gh` not installed), so it was raised before pushing and confirmed as public with everything included. | 2026-09-23 | 15:35 IST | **Taken** | Verified before pushing: no `.venv`, no `.env`, no `projects/`, no `*.local.*`, and no credential values in any tracked file. The `ANTHROPIC_API_KEY` strings a naive grep finds are env-var *names*, which is exactly the distinction `tests/test_secrets/test_repo_hygiene.py` enforces. | **`Plan/CLAUDE.md` is now publicly indexable**, including the "about me" section and working preferences. Reversing this needs a history rewrite plus force-push, not a delete — the cost only grows as commits accumulate. `projects/` stays gitignored, so future ledgers holding verbatim client answers never leave the machine; **keep that exclusion**. | — (repo-level) |
| Bug | #1 | `test_model_strings_live_only_in_the_seam` only scanned `.py` files | The T01 hygiene test enforcing "no model id outside `ppa/providers/model.py`" (decision #2) globbed `.py` sources only. A model id pinned via `ModelConfig.model_override` in `config/model.yaml`, or in any future `.yaml`/`.toml`/`.json` config, would defeat the tier seam completely while the test stayed green — the exact failure mode the user's re-statement of decision #2 called out: *"the automated test should enforce exactly that."* Found by re-reading the test against that re-statement, not by anything actually leaking — a repo-wide grep before the fix found the seam intact. | 2026-09-23 | 16:00 IST | **Resolved** | Not something that failed silently in production — caught by re-checking the test's actual coverage against its stated intent, prompted directly by user feedback. `.md` files were deliberately left out of the widened scan: a decision record quoting `ppa doctor` output as verification evidence (e.g. `t01_environment_and_model_seam.md`) is documentation, not configuration, and doesn't drive runtime behavior. | Widened the scan to `.py`, `.yaml`, `.yml`, `.toml`, `.json`. Added a second, more direct test (`test_shipped_config_names_a_tier_not_a_model_id`) that loads the repo's actual `config/model.yaml` and asserts `model_override is None`. Proved the fix catches the real case: injected `model_override: claude-opus-5` into `config/model.yaml`, watched the test fail with the exact offending file named, then restored the original and confirmed green again. 117 tests passing. | `t01_environment_and_model_seam.md` |
| Bug | #2 | Completed T01 record showed a bare `python` command that was actually run through `.venv/Scripts/python.exe` | While re-verifying decision #3 against the repo, found `completed_tasks/t01_environment_and_model_seam.md`'s "Verification output" transcript read `$ python -m ppa.cli --help` / `$ python -m ppa.cli doctor` / `$ pytest` — bare `python`, no `.venv/` prefix — though the commands actually run in-session used `.venv/Scripts/python.exe` throughout. Cosmetic, not functional: nothing else in the repo (README, scripts, `.gitignore`, the hygiene test) has this inconsistency. But a completed task's verification block is meant to be copy-pastable, and copy-pasting the bare form risks silently running a global interpreter instead of the project's `.venv` — exactly what decision #3 exists to prevent. | 2026-09-23 | 16:08 IST | **Resolved** | Found by checking the user's restated decision #3 against the actual repo state rather than taking the existing row at its word — same diligence as bug #1. | Corrected the three transcript lines in `completed_tasks/t01_environment_and_model_seam.md` to show the `.venv/Scripts/python.exe` prefix that was actually used. Editing a moved task file for factual accuracy (not a redesign) is consistent with the board's own rule of amending before/if a record turns out wrong. | `t01_environment_and_model_seam.md` |
| Decision | #7 | **Status enum for `QuestionAnswer` and `ResearchFinding` — a real gap in DESIGN.md §2.7, now confirmed** | §2.7 gives an explicit status enum for five of the seven entities (Requirement, Assumption, Decision, Unknown, Risk) but not for `QuestionAnswer` or `ResearchFinding`, even though the shared base line requires every entity to carry `status`. The gap was filled by assumption in T02 (`SUPERSEDED` for both) and flagged for confirmation. **User confirmed the enum shape but renamed the terminal value: `REPLACED` instead of `SUPERSEDED`, for both entities** — final enums are `QuestionAnswer: PENDING\|ANSWERED\|REPLACED` and `ResearchFinding: ACTIVE\|REPLACED`. User's stated reason: `REPLACED` "is simpler and clearly communicates that a newer answer or finding has taken its place." Confirmed explicitly that research freshness stays independent of status — `researched_at`/`stale_after_days` track staleness; `REPLACED` only tracks supersession by a newer answer/finding, and a stale finding is not automatically `REPLACED`. | 2026-09-23 | 16:20 IST | **Resolved — confirmed with a rename** | This is the only entity-scoped exception to the `SUPERSEDED` vocabulary used everywhere else (Requirement, Assumption, Decision keep `SUPERSEDED`) — worth remembering when reading `transitions.py` so the two aren't mistaken for a typo. | Updated `ppa/ledger/models.py` (`QuestionAnswer.status`, `ResearchFinding.status`) and `ppa/ledger/transitions.py` (`TRANSITIONS[QUESTION_ANSWER]`, `TRANSITIONS[RESEARCH_FINDING]`) to use `REPLACED`. Updated `tests/test_ledger/test_transitions.py` (`CASES`, the terminal-status parametrize list) to match. Full suite re-run: 117 passed. `completed_tasks/t02_domain_entities_and_status_model.md` build record updated to show the confirmed enums rather than the original assumption. | `t02_domain_entities_and_status_model.md` |
| Blocker | #3 | `ppa/ledger/events.py` carried a stub docstring pointing at the wrong task | T01's scaffold left `events.py` with "Not implemented yet — filled in by T06," but T03's own task file explicitly names `ppa/ledger/events.py` for the Event envelope, and T06's own task file names a different file (`ppa/ledger/store.py`) for the append/lock/fsync mechanism. Same root cause as blocker #2: §2.6 only specifies directories, not every filename, so T01's scaffold guessed a task mapping instead of checking the downstream task files that actually name them. | 2026-09-23 | 16:35 IST (found while reading T03's prerequisites, before writing any code) | **Resolved** | Caught before any code was written against the wrong assumption — cost nothing. No actual file-content conflict existed; only the stub comment was wrong. | Overwrote the stub docstring when building T03's real content. Verified `ppa/ledger/store.py` does not yet exist and carries no conflicting stub, and that `ppa/ledger/secrets.py`'s stub already correctly names T06. No code changes needed beyond T03's own build. | `t03_event_model_and_transactions.md` |
| Decision | #9 | **Four event types added beyond T03's own enumeration, to make status coverage real** | T03 lists event types explicitly but, checked against `ppa/ledger/transitions.py`'s actual `TRANSITIONS` matrix, four reachable statuses had no designated event type: `Assumption.SUPERSEDED`, `Decision.SUPERSEDED`, `QuestionAnswer.REPLACED`, `ResearchFinding.REPLACED`. Without an event type, those real status changes would have nowhere to be recorded, breaking the task's own Done-when box ("every state change maps to exactly one event type"). | 2026-09-23 | 16:40 IST | **Taken** | Not a design call requiring user input — a direct, mechanical consequence of the entity schema already confirmed in T02 (including decision #7's `REPLACED` rename, which is exactly why `QuestionAnswer`/`ResearchFinding` needed `.replaced` rather than `.superseded`). | Added `assumption.superseded`, `decision.superseded`, `question.replaced`, `research.replaced` to `EventType` in `ppa/ledger/events.py`. `Risk` intentionally still has zero event types — T02 declared it "not written in v1." Coverage is asserted by `test_every_reachable_status_has_a_designated_event_type` in `tests/test_ledger/test_events.py`, which fails automatically if a future status is added to `transitions.py` without a matching event type. | `t03_event_model_and_transactions.md` |

**Keeping this current:** when a row in §1–§3 becomes fully resolved, **cut it from its source
table and paste it here**, in the right chronological slot — don't leave a copy behind, and don't
just append to the bottom regardless of when it actually closed. A decision that's `Taken` but
still flagged for confirmation (like #7 was, until the user confirmed it with the `REPLACED`
rename) stays in §2 until the confirmation actually lands; only then does it move here.

---

## Watchlist — risks that have not occurred yet

Not blockers. The things most likely to become a new row in §1 or §3.

| Risk | Bites at | Why it is not a blocker today | Early warning to watch for |
|---|---|---|---|
| **Subscription rate limits** | T23–T34, worst at T34 | The zero-cost path is verified and working. But subscription usage limits are a different constraint from API credits, and nothing in the plan accounts for them. T34 runs an eval suite repeatedly. | Model calls starting to fail or throttle during Phase D. Mitigation is already in place: flip `PPA_MODEL_TIER=cheap` or switch `auth_source` to `api_key` — one config line either way, by design. |
| **`total_cost_usd` is not a bill** | T34 | The SDK reports a cost figure (~$0.17, ~$0.14 on the T01 probes) even with no API key present. That is equivalent-cost accounting on the subscription. | Useful as a *relative* signal when sizing eval runs. Do not budget against it as if it were spend. |
| **The task chain is almost entirely serial** | T13 onward | T02 fans out to T03/T04/T05, and T10–T12 can run in parallel after T07. But T13→T14→…→T35 is a single line, each task gated on the one before it. | A schedule risk, not a correctness one. Only matters if you want to parallelise or bring someone else in. |

---

## How to use this file

**Status column** — one of three values, always, in §1 and §3 (and in the moved-in rows of §4):

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

**Blockers** — add the row to §1 before fixing, while the detail is still exact. Once resolved,
move the whole row to §4 — don't leave a stub behind. If a task file turns out to be wrong, the
board's rule applies: **edit the task file before moving it to `completed_tasks/`**, and record
the amendment here too, so the reason survives alongside the change.

**Decisions** — add a row to §2 for anything chosen *or* deferred. Pending rows carry no date and
a `PENDING` status; leave them in §2 until resolved. Once a decision is genuinely settled (not
just `Taken` but confirmed, with no open follow-up), move it to §4. Anything that closes a
DESIGN.md §6.7 open decision gets ticked there and on the board as well.

**Bugs** — add the row to §3. Code defects only. Include the failing case, not just the symptom.
Once fixed and a test guards it, move the row to §4 and name the test in the fix column.

**§4 is the only section that only grows.** It is the permanent, full-detail archive — never
summarized, never pruned, never left as a stub elsewhere. Everything else in this file is a
snapshot of what's still open right now.
