"""Impact graph — traversal, not an LLM re-deriving relationships
inconsistently on every change (DESIGN.md §1.9, S4.2).

Impact analysis only pays off because provenance links are mandatory at
write time (T16 enforces that; this module just consumes what's already on
the entities). Graph traversal is deterministic, instant, and complete —
exactly the shape of problem that never needs a model.

Naming, so it stays unambiguous: `analyze_impact()` here is an *engine*
function. Agents reach it as `read_planning_state(scope="impact")` (T15).
The v2 Planning Agent's `analyze_plan_impact` is a different, plan-level
operation — don't confuse the two.
"""

from __future__ import annotations

from collections import deque
from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.ledger.models import BaseEntity

_LINK_FIELDS = (
    "derived_from_answers",
    "depends_on_assumptions",
    "depends_on_decisions",
    "affects_requirements",
    "related_requirements",
)
"""Every provenance field DESIGN.md names for this task — deliberately not
extended to every link-shaped field on every entity (e.g. `prerequisites`,
`current_assumption`, `converted_to`, `feeds_decision`): those may earn a
place here once a real traversal needs them, not speculatively now."""


class AffectedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    hop_distance: int
    path: list[str]
    """The full id sequence from the source entity to this one, inclusive
    of both ends."""


class ImpactReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    affected: list[AffectedEntity]
    cycle: list[str] | None = None
    """The id sequence of a cycle found while building the graph, if any —
    `None` means none was found, not that none was checked for."""


def _build_directed_graph(entities: Mapping[str, BaseEntity]) -> dict[str, set[str]]:
    """One edge per provenance reference, in the direction the field itself
    declares (e.g. `Assumption.affects_requirements` -> edges from the
    assumption to each requirement it affects)."""

    graph: dict[str, set[str]] = {entity_id: set() for entity_id in entities}
    for entity_id, entity in entities.items():
        for field in _LINK_FIELDS:
            targets = getattr(entity, field, None)
            if not targets:
                continue
            graph[entity_id].update(targets)
    return graph


def _build_undirected_adjacency(directed: dict[str, set[str]]) -> dict[str, set[str]]:
    """Impact travels both ways — something a changed entity depends on is
    as worth a second look as something that depends on it — so traversal
    uses the undirected view; only cycle detection needs direction."""

    adjacency: dict[str, set[str]] = {node: set(neighbors) for node, neighbors in directed.items()}
    for node, neighbors in directed.items():
        for neighbor in neighbors:
            adjacency.setdefault(neighbor, set()).add(node)
    return adjacency


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """Classic white/gray/black DFS. A gray node reached again is a back
    edge — the cycle is the gray path from that node back to itself,
    reconstructed via `parent`. Returns the first cycle found; this module
    only needs to prove one exists and show it, not enumerate every one."""

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in graph}
    parent: dict[str, str | None] = {}

    def dfs(start: str) -> list[str] | None:
        stack = [(start, iter(sorted(graph.get(start, ()))))]
        color[start] = GRAY
        while stack:
            node, neighbors = stack[-1]
            advanced = False
            for neighbor in neighbors:
                if neighbor not in color:
                    color[neighbor] = WHITE
                if color[neighbor] == WHITE:
                    color[neighbor] = GRAY
                    parent[neighbor] = node
                    stack.append((neighbor, iter(sorted(graph.get(neighbor, ())))))
                    advanced = True
                    break
                if color[neighbor] == GRAY:
                    cycle = [node]
                    cursor = node
                    while cursor != neighbor:
                        cursor = parent[cursor]
                        cycle.append(cursor)
                    cycle.reverse()
                    cycle.append(neighbor)
                    return cycle
            if not advanced:
                color[node] = BLACK
                stack.pop()
        return None

    for start in sorted(graph):
        if color.get(start, WHITE) == WHITE:
            parent[start] = None
            found = dfs(start)
            if found is not None:
                return found
    return None


def analyze_impact(entity_id: str, entities: Mapping[str, BaseEntity]) -> ImpactReport:
    """Every entity reachable from `entity_id` via the provenance graph,
    with hop distance and the path taken to reach it, plus any cycle found
    while building the graph. Terminates on a cyclic graph by construction —
    BFS never revisits a node once it's in `visited` — rather than needing
    special-case cycle-breaking logic of its own."""

    directed = _build_directed_graph(entities)
    adjacency = _build_undirected_adjacency(directed)

    visited: dict[str, tuple[int, list[str]]] = {entity_id: (0, [entity_id])}
    queue: deque[str] = deque([entity_id])
    while queue:
        current = queue.popleft()
        depth, path = visited[current]
        for neighbor in sorted(adjacency.get(current, ())):
            if neighbor in visited:
                continue
            visited[neighbor] = (depth + 1, path + [neighbor])
            queue.append(neighbor)

    affected = [
        AffectedEntity(entity_id=eid, hop_distance=depth, path=path)
        for eid, (depth, path) in visited.items()
        if eid != entity_id
    ]
    affected.sort(key=lambda a: (a.hop_distance, a.entity_id))

    return ImpactReport(source_entity_id=entity_id, affected=affected, cycle=_find_cycle(directed))
