# T11 — Impact graph and conflict detection

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.9, §1.10, §3.7, S4.2, S4.6 |

## Prerequisites

- [ ] **T07**

## Why this task exists

Impact analysis must be graph traversal, not an LLM re-deriving relationships inconsistently on
every change. That only works if provenance links are mandatory at write time — which T16
enforces. This task builds the traversal that makes those links pay off.

## What to build

### Impact graph — `ppa/engines/impact.py`

Build a directed graph from provenance links already on the entities: `derived_from_answers`,
`depends_on_assumptions`, `depends_on_decisions`, `affects_requirements`, `related_requirements`.

`analyze_impact(entity_id) -> ImpactReport` returning affected entity IDs, hop distance, and the
**path** to each. Detect and break cycles rather than looping.

Naming, so it stays unambiguous: `analyze_impact()` is an *engine* function. Agents reach it as
`read_planning_state(scope="impact")` (T15). The Planning Agent's `analyze_plan_impact` in v2 is
a different, plan-level operation.

### Conflict candidates — `ppa/engines/conflicts.py`

`find_conflict_candidates(new_answer, ledger) -> list[Candidate]` — **deterministic first pass
only**. The model adjudicates later (T30); this just finds pairs worth looking at.

Signals: shared coverage areas, shared entity references, negation markers, mutually exclusive
enum values, quantity contradictions.

Tuning target: recall over precision. A missed conflict silently corrupts the ledger; a false
candidate costs one cheap model call.

## Files touched

```
ppa/engines/impact.py
ppa/engines/conflicts.py
tests/test_engines/test_impact.py
tests/test_engines/test_conflicts.py
```

## Done when

- [ ] On a REQ-001 → ASM-002 → DEC-003 fixture, changing REQ-001 returns both, with paths, in under 50ms
- [ ] A cyclic graph terminates and reports the cycle
- [ ] Impact on a 200-entity graph completes in under 200ms
- [ ] The fixture pair \"internal tool, 20 users\" vs \"public launch\" is flagged as a candidate
- [ ] Ten non-conflicting pairs produce zero candidates
- [ ] Conflict detection runs without any model call

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_engines/`
3. Commit: `git add -A && git commit -m "T11: Impact graph and conflict detection"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t11_*.md completed_tasks\
   bash:     mv tasks/t11_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T11` on the board.
