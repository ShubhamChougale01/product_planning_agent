"""Open items tests (T12). Every Done-when box in
tasks/t12_date_rules_and_open_items.md that concerns
`ppa/engines/open_items.py` maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ppa.engines.open_items import collect_open_items
from ppa.ledger.models import Assumption, Decision, Unknown

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _unknown(entity_id: str, **overrides) -> Unknown:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        status="OPEN",
        question=f"question for {entity_id}",
        area="platform",
        why_it_matters="it matters",
        blocking=False,
        route="USER_DECISION",
        owner_type="user",
    )
    base.update(overrides)
    return Unknown(**base)


def _decision(entity_id: str, **overrides) -> Decision:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        status="OPEN",
        question=f"question for {entity_id}",
        blocking=False,
        owner="user:shubham",
        owner_type="user",
        identified_at=NOW,
    )
    base.update(overrides)
    return Decision(**base)


def _assumption(entity_id: str, **overrides) -> Assumption:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        status="PROPOSED",
        statement=f"assumption for {entity_id}",
        reason="inferred",
        impact="HIGH",
        confidence="MEDIUM",
        confidence_basis="strongly implied",
    )
    base.update(overrides)
    return Assumption(**base)


# ---------------------------------------------------------------------------
# Done when: open items output matches the §3.8 board layout from fixture
# data.
# ---------------------------------------------------------------------------


def test_collects_every_kind_named_in_the_task_and_no_others():
    entities = {
        "UNK-001": _unknown("UNK-001", blocking=True, status="OPEN"),
        "UNK-002": _unknown("UNK-002", blocking=False, route="RESEARCH", status="OPEN"),
        "UNK-003": _unknown("UNK-003", blocking=False, route="USER_DECISION", status="OPEN"),
        "UNK-004": _unknown("UNK-004", blocking=True, status="RESOLVED"),  # resolved, excluded
        "DEC-001": _decision("DEC-001", status="OPEN"),
        "DEC-002": _decision("DEC-002", status="DECIDE_LATER"),
        "DEC-003": _decision("DEC-003", status="DECIDED"),  # settled, excluded
        "ASM-001": _assumption("ASM-001", impact="HIGH", status="PROPOSED"),
        "ASM-002": _assumption("ASM-002", impact="HIGH", status="CONFIRMED"),  # settled, excluded
        "ASM-003": _assumption("ASM-003", impact="LOW", status="PROPOSED"),  # not HIGH, excluded
    }

    items = collect_open_items(entities)
    ids = {item.entity_id for item in items}

    assert ids == {"UNK-001", "UNK-002", "DEC-001", "DEC-002", "ASM-001"}


def test_each_item_carries_owner_owner_type_due_date_blocking_and_resolution():
    entities = {"DEC-001": _decision("DEC-001", status="OPEN", blocking=True, owner="user:shubham", owner_type="user", expected_decision_date=NOW + timedelta(days=2))}
    item = collect_open_items(entities)[0]

    assert item.owner == "user:shubham"
    assert item.owner_type == "user"
    assert item.due_date == NOW + timedelta(days=2)
    assert item.blocking is True
    assert item.resolution


def test_blocking_unknown_and_research_routed_unknown_appear_once_each():
    entities = {
        "UNK-005": _unknown("UNK-005", blocking=True, route="RESEARCH", status="OPEN"),
    }
    items = collect_open_items(entities)
    assert len(items) == 1
    assert items[0].kind == "blocking_unknown"  # blocking takes priority over research-queued


# ---------------------------------------------------------------------------
# Done when: externally-owned items are visibly distinguished from
# user-owned ones.
# ---------------------------------------------------------------------------


def test_externally_owned_items_are_distinguished_from_user_owned():
    entities = {
        "DEC-001": _decision("DEC-001", status="OPEN", owner_type="external"),
        "DEC-002": _decision("DEC-002", status="OPEN", owner_type="user"),
    }
    items = {item.entity_id: item for item in collect_open_items(entities)}

    assert items["DEC-001"].owner_type == "external"
    assert items["DEC-002"].owner_type == "user"
    assert items["DEC-001"].owner_type != items["DEC-002"].owner_type


# ---------------------------------------------------------------------------
# Done when: overdue items sort above merely-due ones.
# ---------------------------------------------------------------------------


def test_overdue_items_sort_above_merely_due_ones():
    entities = {
        "DEC-001": _decision("DEC-001", status="OPEN", expected_decision_date=NOW + timedelta(days=5)),
        "DEC-002": _decision("DEC-002", status="OPEN", expected_decision_date=NOW - timedelta(days=1)),
        "DEC-003": _decision("DEC-003", status="OPEN", expected_decision_date=NOW + timedelta(days=1)),
    }
    items = collect_open_items(entities)
    assert [item.entity_id for item in items] == ["DEC-002", "DEC-003", "DEC-001"]


def test_items_with_no_due_date_sort_after_items_with_one():
    entities = {
        "ASM-001": _assumption("ASM-001", impact="HIGH", status="PROPOSED"),  # no due date
        "DEC-001": _decision("DEC-001", status="OPEN", expected_decision_date=NOW + timedelta(days=1)),
    }
    items = collect_open_items(entities)
    assert [item.entity_id for item in items] == ["DEC-001", "ASM-001"]


def test_blocking_breaks_a_tie_with_warning_severity_at_the_same_due_date():
    entities = {
        "ASM-001": _assumption("ASM-001", impact="HIGH", status="PROPOSED"),  # warning, no due date
        "UNK-001": _unknown("UNK-001", blocking=True, status="OPEN"),  # blocking, no due date
    }
    items = collect_open_items(entities)
    assert items[0].entity_id == "UNK-001"
    assert items[0].severity == "blocking"
