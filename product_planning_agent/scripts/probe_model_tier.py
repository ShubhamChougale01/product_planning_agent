"""T34 decision #4 probe: which model tier for eval runs?

Runs the same real INTAKE turn (T24's own worked example: "a tool for
tracking vendor invoices") once per tier (`cheap`, `primary`, `deep`),
setting `PPA_MODEL_TIER` before each — the wiring this task's own fix
(`ppa.providers.model.ModelProvider.from_config`, now actually called by
every real turn) makes meaningful for the first time. Measures wall-clock
latency, `ResultMessage.total_cost_usd` (an equivalent-cost signal under
subscription auth, per `docs/decisions/auth.md`'s own caveat — not a
metered charge) and pass/fail against `ppa.agents.modes.intake.
evaluate_intake_shape`, the same quality bar `tests/eval/test_intake.py`
already holds every INTAKE turn to.

Run with:

    cd product_planning_agent
    .venv/Scripts/python.exe scripts/probe_model_tier.py

Not a pytest test — a one-off, re-runnable probe, the same shape
`scripts/verify_auth.py` already established for decision #1/#2/#3.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

from ppa.agents.discovery import DiscoveryAgent
from ppa.agents.modes.intake import evaluate_intake_shape
from ppa.config.profiles import UserProfile
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.tools.dispatch import InvocationContext

TIERS = ("cheap", "primary", "deep")
SEED_REQUIREMENT = "a tool for tracking vendor invoices"


def _profile() -> UserProfile:
    return UserProfile(role="engineer", technical_depth="medium", domain_familiarity="medium")


def _ctx(project) -> InvocationContext:
    return InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="probe-model-tier", audit_path=project.audit_path,
    )


def probe_one_tier(tier: str, tmp_root: Path) -> dict:
    os.environ["PPA_MODEL_TIER"] = tier
    project = create_project(
        f"Model Tier Probe {tier}", SEED_REQUIREMENT, _profile(), projects_root=tmp_root / tier,
    )

    started = time.monotonic()
    result = DiscoveryAgent().invoke(_ctx(project))
    elapsed = time.monotonic() - started

    entities = current_entities(project.events_path)
    shape = evaluate_intake_shape(entities, reply_text=result.summary)

    return {
        "tier": tier,
        "elapsed_seconds": round(elapsed, 1),
        "cost_usd": result.data.get("cost_usd") if result.data else None,
        "shape_ok": shape.ok,
        "shape_violations": shape.violations,
        "status": result.status.value,
    }


def main() -> int:
    import tempfile

    print(f"{'tier':<10}{'model':<26}{'elapsed(s)':>12}{'cost(usd)':>12}{'shape_ok':>10}")
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for tier in TIERS:
            row = probe_one_tier(tier, tmp_root)
            results.append(row)
            from ppa.providers.model import MODEL_TIERS

            print(
                f"{row['tier']:<10}{MODEL_TIERS[row['tier']]:<26}{row['elapsed_seconds']:>12}"
                f"{str(row['cost_usd']):>12}{str(row['shape_ok']):>10}"
            )
            if not row["shape_ok"]:
                print(f"    violations: {row['shape_violations']}")

    print()
    for row in results:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
