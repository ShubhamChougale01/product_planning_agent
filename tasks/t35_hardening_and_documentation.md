# T35 — Hardening and documentation

| | |
|---|---|
| **Phase** | F · Resilience and validation |
| **Estimate** | 1 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §2.16, §6.6, S13.1–S13.5 |

## Prerequisites

- [ ] **T34**

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

## Done when

- [ ] A killed session resumes with no manual repair
- [ ] A week-old project resumes with full context from the digest
- [ ] `ppa why <id>` reports agent, tool and workflow state, not just the change
- [ ] Token cost is broken down per agent and per mode
- [ ] README documents all seven commands with one worked example
- [ ] The single-writer constraint is stated explicitly in the README
- [ ] The ledger-contents notice is in the README and shown on `ppa new`
- [ ] All three open decisions from §6.7 are resolved and recorded

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
