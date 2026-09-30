"""Context assembly for one agent turn (T21, DESIGN.md §1.11, §2.11, §2.18).

**Policy: system prompt + digest + last N turns. Never the raw ledger.**
`ppa.ledger.digest.generate_digest` (T09) already renders the bounded,
asymmetric digest half of that; this module owns the other half — turning
`events.ndjson` into a bounded history of *rounds* the digest doesn't cover.

**A round is one outer-loop iteration.** `ppa/orchestrator/loop.py` opens one
`txn.begin`/`txn.commit` pair per iteration (DESIGN.md §2.14, §2.11 step 6),
so grouping events by `txn_id` reconstructs exactly the round boundaries the
loop itself drew — no separate round counter needs to exist anywhere.
Events outside any transaction (`project.created`, `user.forced_ready`, and
so on) are not part of any round and are not shown here; they are either
one-off (already in the digest's own project header) or not narrative
content a turn-history section is for.

`N` (`recent_rounds`) is configurable, default 6. Rounds beyond the most
recent `N` are not dropped — each still contributes its own one-line
`gitops.summarize_turn` summary (questions asked, answers received, entities
created), just folded into an "earlier rounds" section instead of a
per-round "recent rounds" one. That is what keeps a 20+ round session
bounded: growth is one short line per round, never a raw event dump, and
never left to the SDK's own generic compaction — which has no way to know a
blocking item must survive and a title-only entity need not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.config.areas import AreaStatus
from ppa.ledger.digest import estimate_tokens, generate_digest
from ppa.ledger.events import Event, EventType
from ppa.ledger.gitops import summarize_turn
from ppa.ledger.models import BaseEntity
from ppa.ledger.project import Project

DEFAULT_RECENT_ROUNDS = 6
"""DESIGN.md §2.11's own number: "Make N configurable, default 6 turns.
Measure before tuning it.\""""

DEFAULT_MAX_CONTEXT_TOKENS = 8_000
"""The configured context budget `ppa/orchestrator/loop.py` logs against
each turn, and `tests/test_agents/test_loop.py` asserts a 20-round fixture
stays under. `ppa.ledger.digest`'s own docstring puts the digest alone at
"~1.5-2k tokens"; this leaves ample room for round history on top of it
without inviting the false precision a tighter number would imply — nothing
here is measured against a real tokenizer (`estimate_tokens`'s own
~4-chars-per-token heuristic), so the budget is deliberately round."""


def read_events(events_path: Path | str) -> list[Event]:
    """Every event in `events_path`, in log order. Reading raw NDJSON
    directly (rather than importing `ppa.ledger.materialize`'s private
    reader) matches this codebase's own established pattern for a module
    that only needs the event stream, not a materialized fold —
    `ppa.ledger.digest._seed_requirement` does the same thing for the same
    reason."""

    events_path = Path(events_path)
    if not events_path.exists():
        return []
    events: list[Event] = []
    with events_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                events.append(Event.model_validate_json(line))
    return events


@dataclass(frozen=True)
class RoundRecord:
    """One outer-loop iteration's worth of events, identified by the
    `txn_id` `ppa/orchestrator/loop.py` opened for it."""

    txn_id: str
    events: tuple[Event, ...]

    def summary(self) -> str:
        return summarize_turn(self.events)


def rounds_from_events(events: list[Event]) -> list[RoundRecord]:
    """Group `events` by `txn_id`, in the order each `txn_id` first
    appears — a round's events stay in log order within the round, and
    rounds themselves stay in the order they happened.

    Only transactions that reached `txn.commit` become a round — the same
    "no matching commit means it never happened" rule
    `ppa.ledger.materialize._effective_events` applies when folding entity
    state, applied here so an aborted round never shows up in a turn's
    history as if it were real progress."""

    committed = {e.txn_id for e in events if e.type is EventType.TXN_COMMIT and e.txn_id}

    order: list[str] = []
    grouped: dict[str, list[Event]] = {}
    for event in events:
        if event.txn_id is None or event.txn_id not in committed:
            continue
        if event.txn_id not in grouped:
            grouped[event.txn_id] = []
            order.append(event.txn_id)
        grouped[event.txn_id].append(event)
    return [RoundRecord(txn_id=txn_id, events=tuple(grouped[txn_id])) for txn_id in order]


def events_for_txn(events_path: Path | str, txn_id: str) -> list[Event]:
    """Every event carrying `txn_id`, in log order — what
    `ppa.ledger.gitops.commit_turn` needs to render this round's commit
    message once it is committed."""

    return [e for e in read_events(events_path) if e.txn_id == txn_id]


class ContextBundle(BaseModel):
    """What one agent turn actually sees, plus the accounting T35's cost
    instrumentation reads (DESIGN.md §2.11: "log the assembled context size
    per turn")."""

    model_config = ConfigDict(extra="forbid")

    text: str
    token_estimate: int
    round_count: int
    recent_round_count: int
    older_round_count: int


def assemble_context(
    project: Project,
    entities: Mapping[str, BaseEntity],
    *,
    coverage: Mapping[str, AreaStatus | str] | None = None,
    round_number: int | None = None,
    now=None,
    recent_rounds: int = DEFAULT_RECENT_ROUNDS,
) -> ContextBundle:
    """`digest + last N rounds in full, everything older summarized` — never
    the raw ledger. `entities` must already be a materialized snapshot
    (`ppa.ledger.materialize.current_entities`'s own return shape), the same
    contract `generate_digest` itself has — this function does no
    materialization of its own, only one more small read of `events.ndjson`
    for round history."""

    digest_text = generate_digest(
        project, entities, coverage=coverage, round_number=round_number, now=now
    )

    rounds = rounds_from_events(read_events(project.events_path))
    recent = rounds[-recent_rounds:] if recent_rounds > 0 else []
    older = rounds[: len(rounds) - len(recent)]

    lines = [digest_text, "", f"## Recent rounds (last {recent_rounds})"]
    if recent:
        lines.extend(f"- {r.txn_id}: {r.summary()}" for r in recent)
    else:
        lines.append("(none yet)")

    if older:
        lines.append("")
        lines.append(f"## Earlier rounds ({len(older)}, summarized)")
        lines.extend(f"- {r.txn_id}: {r.summary()}" for r in older)

    text = "\n".join(lines)
    return ContextBundle(
        text=text,
        token_estimate=estimate_tokens(text),
        round_count=len(rounds),
        recent_round_count=len(recent),
        older_round_count=len(older),
    )
