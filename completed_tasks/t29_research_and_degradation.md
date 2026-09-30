# T29 — Research mode and provider degradation

| | |
|---|---|
| **Phase** | D · Discovery Agent — the intelligence layer |
| **Estimate** | 0.75 day |
| **Needs a model?** | Yes + web |
| **Design reference** | DESIGN.md §6.5, §2.12, S9.4–S9.5 |

## Prerequisites

- [ ] **T28**

## Why this task exists

Research is a capability that may simply be absent — T01 determined whether web search exists on
your auth path. Absence must degrade honestly rather than stall planning or, far worse, produce
a confident fabricated answer.

## What to build

### Provider — `ppa/providers/research.py`

```python
class ResearchProvider(Protocol):
    def available(self) -> bool: ...
    def research(self, question, context) -> ResearchResult: ...
```

Three states, three behaviours:

```
AVAILABLE    research; write RES-nnn with sources and researched_at
UNAVAILABLE  item stays route=RESEARCH, blocked_reason="no_research_capability",
             owner flips to user, appears in open items.
             Agent says plainly: "I can't research this here. From what I know:
             <degraded answer>. Worth verifying."   -> degraded=True
FAILED       retry once, then treat as UNAVAILABLE and say which — a failed search
             and no search capability are different situations for the user
```

### Gate rule — the decision that matters

An unresearched item blocks READY **only if it is itself blocking** (`blocking=true`). Otherwise
it is a tracked open item and planning continues. Without this, one unavailable web search stalls
the entire session. Already implemented in T10; verify end-to-end.

### Staleness

Technical recommendations age badly — a database comparison from eight months ago is misleading,
not merely old. Every finding carries `researched_at` and `stale_after_days` (default 90). The
status board flags stale findings that still underpin an open decision.

## Files touched

```
ppa/providers/research.py
ppa/agents/subagents/research.py
tests/eval/test_research.py
```

## Done when

- [x] With research **disabled**, a session still reaches READY — verified end-to-end against the readiness gate's own condition 2 (already built, T10; non-blocking is what exempts it, regardless of route)
- [x] Every unresearched item appears in open items with an honest explanation
- [x] The agent never fabricates a researched answer when the provider is unavailable — no `ResearchFinding` is ever created on the degraded path
- [x] `degraded=True` is set on reduced-capability success
- [x] A failed search and an unavailable provider produce **different** messages
- [x] Findings older than 90 days are flagged STALE when they underpin an open decision
- [x] Empty research results return success, not an error, and are never retried

## Build record

`ppa/providers/research.py` — `ResearchProvider` (Protocol), `ResearchResult`, and three builder
functions (`unavailable_result`/`failed_result`/`empty_result`) each producing §6.5's own exact
plain-language framing. `NullResearchProvider` (always `UNAVAILABLE`) and `SdkWebSearchResearch
Provider` (always `AVAILABLE` in this environment, decision #5) both satisfy the Protocol.

`ppa/agents/subagents/research.py` — `run_research_session` batches the *entire* open
`RESEARCH_REQUIRED` queue in one turn (S9.4), same isolated-context shape as T28's Guidance
subagent. `provider.available()` gates before any model call; a real attempt that raises is
retried once, then degrades with a distinct message. `_degrade_unknown` folds an honest
explanation into `why_it_matters` and flips `owner_type` to `"user"` via `manage_unknown
(classify)`, widened to accept `owner_type` for exactly this. `stale_findings_underpinning_open_
decisions` is the staleness half.

**Decision #37** (`blockers.md`): three related calls — `blocked_reason` folded into
`why_it_matters` rather than a new schema field; `available()` checked before any model call
(zero cost for the UNAVAILABLE path); the FAILED-path message built directly via `failed_result`
rather than through `provider.research()` (deliberately unimplemented on the real provider — see
its own docstring).

`tests/test_agents/test_registry.py::test_research_invoke_also_returns_structured_not_implemented`
(T28's own narrowed version of the original combined test) removed outright — Research is now the
last of the two agents to get real behavior, nothing left in that test to assert.

Tests: `tests/eval/test_research.py` (11 mechanical, zero-cost; 1 `live_model`). Full suite
re-run: **813 passed** (803 baseline − 1 removed + 11 new), 1 skipped, default run; `pytest -m
live_model`: 7 passed (T23, T24, T25, T26, T27, T28, T29) — clean, no flake this run.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T29: Research mode and provider degradation"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t29_*.md completed_tasks\
   bash:     mv tasks/t29_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T29` on the board.
