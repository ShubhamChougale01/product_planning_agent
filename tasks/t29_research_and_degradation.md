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

- [ ] With research **disabled**, a session still reaches READY
- [ ] Every unresearched item appears in open items with an honest explanation
- [ ] The agent never fabricates a researched answer when the provider is unavailable
- [ ] `degraded=True` is set on reduced-capability success
- [ ] A failed search and an unavailable provider produce **different** messages
- [ ] Findings older than 90 days are flagged STALE when they underpin an open decision
- [ ] Empty research results return `success=True, result_count=0` — not an error, and not retried

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
