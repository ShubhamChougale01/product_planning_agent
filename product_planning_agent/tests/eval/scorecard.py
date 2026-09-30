"""T34 — the "one command prints a scorecard" Done-when box.

    python -m tests.eval.scorecard                       # deterministic cases only (fast, no model call)
    python -m tests.eval.scorecard --live                 # + the four live cases (real model calls)
    python -m tests.eval.scorecard --matrix               # + a real fixture x persona session (slow)
    python -m tests.eval.scorecard --matrix --fixture f06_detailed_k8s_audit_alerting --persona always_idk
    python -m tests.eval.scorecard --save tests/eval/baseline.json

Runs every case in `tests.eval.cases.CASE_MODULE_NAMES`, in order — `--live`
opts into the four in `LIVE_CASE_MODULE_NAMES` as well (real model calls,
real cost, real latency; omitted by default, the same "opt in explicitly"
shape `pytest -m live_model` already uses). `--matrix` additionally drives
one real `tests.eval.harness.run_session` per requested (fixture, persona)
pair (default: every fixture x every persona — very slow; narrow it with
`--fixture`/`--persona`, repeatable) and folds each into a `SessionMetrics`
row. `--save PATH` writes the resulting `Scorecard.model_dump()` as JSON;
run again later with `--compare PATH` to print `compare_scorecards`'s own
delta against a previously recorded baseline.
"""

from __future__ import annotations

import argparse
import importlib
import json
import tempfile
from pathlib import Path

from ppa.engines.coverage import progress
from ppa.ledger.materialize import current_entities
from tests.eval.cases import CASE_MODULE_NAMES, LIVE_CASE_MODULE_NAMES
from tests.eval.harness import PERSONAS, load_fixture, load_fixtures, run_session
from tests.eval.rubric import CaseOutcome, SessionMetrics, Scorecard, compare_scorecards, compute_scorecard


def _run_cases(*, include_live: bool, tmp_root: Path) -> list[CaseOutcome]:
    outcomes: list[CaseOutcome] = []
    for module_name in CASE_MODULE_NAMES:
        if module_name in LIVE_CASE_MODULE_NAMES and not include_live:
            continue
        module = importlib.import_module(module_name)
        case_dir = tmp_root / module_name.rsplit(".", 1)[-1]
        case_dir.mkdir(parents=True, exist_ok=True)
        outcome = module.run_case(case_dir)
        outcomes.append(outcome)
        marker = "PASS" if outcome.passed else "FAIL"
        print(f"[{marker}] {outcome.case_id} — {outcome.name}")
        if not outcome.passed:
            print(f"       {outcome.notes}")
    return outcomes


def _run_matrix(*, fixture_names: list[str] | None, persona_names: list[str] | None, max_rounds: int, tmp_root: Path) -> list[SessionMetrics]:
    fixtures = [load_fixture(name) for name in fixture_names] if fixture_names else load_fixtures()
    personas = persona_names or list(PERSONAS)

    metrics: list[SessionMetrics] = []
    for fixture in fixtures:
        for persona_name in personas:
            report = run_session(fixture, PERSONAS[persona_name], projects_root=tmp_root / "projects", max_rounds=max_rounds)
            questions_asked = sum(len(r.questions_answered) for r in report.rounds)
            coverage_at_gate = None
            if report.project is not None:
                entities = current_entities(report.project.events_path)
                n_sufficient, n_critical = progress(entities, report.project.profile)
                coverage_at_gate = None if n_critical == 0 else n_sufficient / n_critical

            metrics.append(
                SessionMetrics(
                    fixture=report.fixture, persona=report.persona,
                    rounds_to_gate=len(report.rounds) if report.ready else None,
                    questions_asked_to_gate=questions_asked, coverage_at_gate=coverage_at_gate,
                )
            )
            status = "BROKE" if report.broke else "ok"
            print(f"[{status}] matrix: {report.fixture} x {persona_name}: {report.stopped_reason}, ready={report.ready}")
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="include the four live-model cases (1, 3, 13, 14)")
    parser.add_argument("--matrix", action="store_true", help="also run a real fixture x persona session matrix")
    parser.add_argument("--fixture", action="append", help="fixture name(s) for --matrix; default: all ten")
    parser.add_argument("--persona", action="append", help="persona name(s) for --matrix; default: all six")
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--save", type=Path, help="write the scorecard as JSON to this path")
    parser.add_argument("--compare", type=Path, help="print a delta against a previously saved scorecard JSON")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        cases = _run_cases(include_live=args.live, tmp_root=tmp_root)
        sessions: list[SessionMetrics] = []
        if args.matrix:
            sessions = _run_matrix(
                fixture_names=args.fixture, persona_names=args.persona, max_rounds=args.max_rounds, tmp_root=tmp_root,
            )

    scorecard = compute_scorecard(cases, sessions)
    print()
    print(scorecard.render())

    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        print()
        print(compare_scorecards(baseline, scorecard))

    if args.save:
        args.save.write_text(json.dumps(scorecard.model_dump(), indent=2, default=str), encoding="utf-8")
        print(f"\nsaved to {args.save}")

    return 0 if scorecard.cases_passed == scorecard.total_cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
