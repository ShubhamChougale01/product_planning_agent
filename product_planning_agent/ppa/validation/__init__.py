"""The five validation layers (DESIGN.md §2.13), plus `infer_validation_
layer` — the observability piece T19 exists to add (its own task file:
"every rejection records `validation_layer_failed` in the audit log").

`ppa/tools/discovery_tools.py` (T16), `ppa/tools/interaction.py` (T17) and
`ppa/tools/delivery_tools.py` (T18) each self-record their own audit trail
(decision #24, `blockers.md`) and already tag every rejection's
`ErrorInfo.category`/`code` precisely. Rather than retrofit a `layer=`
keyword onto every one of their `_error(...)` call sites, this module
infers the layer from that same category/code — one shared lookup, called
once per audit record, at the point each module already builds one. A code
this table doesn't recognize maps to `None`, same as a category this
table doesn't handle (`TRANSIENT`, `NOT_IMPLEMENTED`) — `None` is a correct
answer, not a bug, for a failure that isn't one of the five layers at all
(a stub's `NOT_IMPLEMENTED`, or the approval gate's own separate gate,
§2.19.2 — see decision #25's own note that approval is deliberately not
one of the five).
"""

from __future__ import annotations

from ppa.results.categories import ErrorCategory
from ppa.results.envelope import ErrorInfo

_CODE_TO_LAYER: dict[str, str] = {
    # Layer 2 — schema: missing/invalid fields, bad batch shape, bad enum.
    "MISSING_REQUIRED_FIELD": "schema",
    "MISSING_COVERS_AREAS": "schema",
    "MISSING_PROVENANCE": "schema",
    "MISSING_ANY_OF": "schema",
    "MISSING_ENTITY_ID": "schema",
    "MISSING_TEXT": "schema",
    "MISSING_WHY_ASKED": "schema",
    "MISSING_ANSWER_TEXT": "schema",
    "MISSING_STORY_IDS": "schema",
    "MISSING_PROJECT_SLUG": "schema",
    "INVALID_ANSWER_KIND": "schema",
    "INVALID_FORMAT": "schema",
    "BATCH_TOO_LARGE": "schema",
    "EMPTY_BATCH": "schema",
    "UNKNOWN_OPERATION": "schema",
    "SCHEMA_INVALID": "schema",
    # Layer 3 — workflow: illegal given the *global* workflow state.
    "ILLEGAL_WORKFLOW_STATE": "workflow",
    # Layer 4 — semantic: a content-level business rule about an entity.
    "AREA_BLOCKED": "semantic",
    "PLAN_NOT_APPROVED": "semantic",
    # Layer 5 — consistency: dangling refs, illegal status transitions.
    "ILLEGAL_TRANSITION": "consistency",
    "NOT_FOUND": "consistency",
    "DANGLING_REFERENCE": "consistency",
}
"""Deliberately excludes the approval gate's own codes (`APPROVAL_
REQUIRED`/`APPROVAL_EXPIRED`/`APPROVAL_SCOPE_MISMATCH`) — approval is a
sixth, separate gate (§2.19.2: "permission asks *may this agent*; approval
asks *does the user want it*"), not one of the five layers, so it correctly
infers to `None` here rather than being force-fit into one."""


def infer_validation_layer(error: ErrorInfo | None) -> str | None:
    """Which of the five layers `error` failed at, or `None` if it isn't
    one of the five (not an error itself — a `TRANSIENT` failure, a stub's
    `NOT_IMPLEMENTED`, or the approval gate's own codes, all correctly
    report `None` here)."""

    if error is None:
        return None
    if error.category == ErrorCategory.PERMISSION:
        return "permission"
    if error.category in (ErrorCategory.TRANSIENT, ErrorCategory.NOT_IMPLEMENTED):
        return None
    return _CODE_TO_LAYER.get(error.code)
