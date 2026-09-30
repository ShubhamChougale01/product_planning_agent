# T33 — Eval fixtures and personas

| | |
|---|---|
| **Phase** | F · Resilience and validation |
| **Estimate** | 0.75 day |
| **Needs a model?** | Yes |
| **Design reference** | DESIGN.md §1.14, S12.1 |

## Prerequisites

- [x] **T31**

## Why this task exists

You cannot improve what you do not measure, and without this you will tune prompts by vibes and
regress silently. Fixtures must be hard enough to break the agent — if none do, they are too easy
to be useful.

## What to build

### Ten seed requirements

Spanning the real spread:
- vague ↔ detailed
- B2B ↔ consumer
- greenfield ↔ legacy integration
- engineer-authored ↔ product-authored
- internal tool ↔ client project (exercises T27)

Keep them one or two lines each — that is what users actually type.

### Six scripted personas

| Persona | Behaviour |
|---|---|
| `knows_their_stuff` | Detailed, consistent answers |
| `vague` | Short, non-committal answers |
| `always_idk` | "I don't know" to everything — must still terminate (T26) |
| `contradicts_self` | Round 4 contradicts round 1 — must be caught (T30) |
| `impatient` | "Just build it", pushes to skip — gate must hold |
| `defers_to_client` | "That's the client's call" — must produce a questionnaire (T27) |

Each persona is a deterministic function from question → answer, so runs are reproducible.

## Files touched

```
tests/eval/fixtures/*.yaml
tests/eval/personas.py
tests/eval/harness.py
```

## Done when

- [x] Ten fixtures, covering every axis listed above
- [x] Six personas, each able to complete a session unattended
- [x] **At least two fixtures break the agent on first run** — if none do, they are too easy
- [x] Persona responses are deterministic and reproducible across runs
- [x] A full fixture × persona run can be launched with one command

## Build record

**Ten fixtures** (`tests/eval/fixtures/*.yaml`) — each tagged with its own `axes` dict
(`detail`/`market`/`system`/`author`/`ownership`); every one of the five axes has both endpoints
represented at least twice across the set (`test_every_axis_has_both_endpoints_represented_across_
the_set`). Two are flagged `adversarial: true` (`f09_self_contradictory_scope`,
`f10_almost_no_content`) — a self-contradictory scope and a near-empty seed — as the set's own
declared candidates for "breaks the agent," verified empirically below rather than assumed from
the flag alone.

**Six personas** (`tests/eval/personas.py`) — one dataclass per row of this task's own table,
registered in `PERSONAS: dict[str, Callable[[], Persona]]` (a factory per name, never a shared
instance). Only `contradicts_self` carries real state (which area it first committed to, whether
it has already reversed one) — every other persona is a pure function of the question alone.
Determinism is proven directly: two fresh instances of the same persona, given the identical
question sequence, produce the identical answer sequence
(`test_persona_responses_are_deterministic_given_the_same_question_sequence`).

**The harness** (`tests/eval/harness.py`) — `run_session(fixture, persona_factory, ...)` drives one
real, multi-round Discovery session: invoke `DiscoveryAgent().invoke(ctx)` (a live model call),
find every `QuestionAnswer` left `PENDING`, hand each to the persona, record the answer via
`ppa.tools.interaction.answer_pending_question` (T31), invoke again — until no questions remain, an
unrecoverable `AgentResult` or exception occurs (`report.broke = True`, with a stated reason, never
a bare crash), or `max_rounds` is reached. Launchable as one command per this task's own Done-when
box: `python -m tests.eval.harness [--fixture NAME ...] [--persona NAME ...] [--max-rounds N]`.

**Live proof** (`tests/eval/test_matrix.py`, `pytest -m live_model`, real Sonnet-5 calls throughout
— `ModelConfig`'s own default tier; `PPA_MODEL_TIER` is not yet wired into real Discovery turns,
decision #4's own still-pending scope, not this task's to fix):

- `test_every_persona_completes_a_session_unattended` (parametrized, all six) — every persona ran
  4-5 real rounds against `f06_detailed_k8s_audit_alerting` without crashing or escalating.
  `impatient` was additionally checked to never talk the gate into READY despite five straight
  `decide_later` answers.
- `test_at_least_two_fixtures_break_the_agent_on_first_run` — one real INTAKE round per fixture,
  `knows_their_stuff`; "broke" means a hard failure *or* a real turn that fails T24's own
  `evaluate_intake_shape` bar. **Passed** — at least two of the ten genuinely broke, on the first
  attempt, with no persona chosen to make that happen.
- `test_defers_to_client_routes_at_least_one_item_externally` — **an honest finding, corrected
  in-flight.** The first live run used `f06` (a purely internal Kubernetes tool with no client
  anywhere in its own seed requirement) and produced zero externally-owned `Unknown`s. On
  inspection this is *correct* agent behavior, not a defect: `needs_external_input` routing (T27)
  depends on context actually naming a client, not on the answer's wording alone, and nothing in
  `f06`'s own project ever established one. The test was fixed to use
  `f03_vague_legacy_invoicing_client` (a real client-project fixture) instead, re-run live, and
  passed. Recorded here rather than silently rerun and forgotten — the same "record what actually
  happened" standard `blockers.md` decisions #33/#34 already established.

Full live run: 8/8 passing after the fixture correction above (7/8 on the first pass, the one
failure being the test's own fixture choice, not the agent). Full non-live suite unaffected:
zero-cost tests in `tests/eval/test_fixtures_and_personas.py` (8 tests) run in the default suite.

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/eval/`
3. Commit: `git add -A && git commit -m "T33: Eval fixtures and personas"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t33_*.md completed_tasks\
   bash:     mv tasks/t33_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T33` on the board.
