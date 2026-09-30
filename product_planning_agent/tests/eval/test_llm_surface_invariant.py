"""T34 — DESIGN.md §2.17 invariant: no model call originates outside the
four LLM surfaces (interpretation, question generation, guidance,
narration).

This is a static seam scan, not a live proof — the invariant is about
*where in the source tree* a real model call can be constructed from, which
a grep over `ppa/` answers deterministically and cheaply, the same
"seam-scan" shape `test_model_provider.py::test_shipped_config_names_a_tier_
not_a_model_id` already uses for a different seam. No model call is made by
this test.

**What "instrument" means here**: every module that ever builds a real
`ClaudeSDKClient` (via `ModelProvider(...).client(...)`) declares its own
module-level `LLM_SURFACE` — a non-empty subset of `ppa.providers.model.
LLM_SURFACES` — right next to the model call. This test does two things,
either of which catches drift:

1. Greps every `.py` file under `ppa/` (test files excluded — they build
   `ModelProvider` directly to test the seam itself, never to run a real
   turn) for the literal `.client(` call — the one method that actually
   resolves credentials and builds a `ClaudeSDKClient` (`ModelProvider.
   describe()`, used by `ppa/cli.py doctor`, constructs a provider only to
   print its config and is correctly *not* a real model call site) — and
   asserts the resulting file set is *exactly* `_EXPECTED_SITES`. A new call
   site with no entry here fails loudly, rather than silently shipping
   uninstrumented.
2. Imports each of those five modules and asserts `LLM_SURFACE` is defined,
   non-empty, and a subset of the canonical four.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ppa.providers.model import LLM_SURFACES

_PPA_ROOT = Path(__file__).resolve().parents[2] / "ppa"

_CLIENT_CALL_PATTERN = re.compile(r"\.client\s*\(")

_EXPECTED_SITES: frozenset[str] = frozenset({
    "ppa/agents/turn.py",
    "ppa/agents/modes/review.py",
    "ppa/agents/modes/change.py",
    "ppa/agents/subagents/guidance.py",
    "ppa/agents/subagents/research.py",
})
"""Every real, non-test module that calls `ModelProvider(...).client(...)`
today — i.e. actually builds a `ClaudeSDKClient` rather than merely
constructing a `ModelProvider` to inspect its config (`ppa/cli.py doctor`).
`ppa/providers/model.py` itself is excluded — `ModelProvider.client` is
defined there but never called at module scope."""


def _modules_calling_client() -> frozenset[str]:
    found: set[str] = set()
    for path in _PPA_ROOT.rglob("*.py"):
        if path.name == "model.py" and path.parent.name == "providers":
            continue
        text = path.read_text(encoding="utf-8")
        if _CLIENT_CALL_PATTERN.search(text):
            found.add(path.resolve().relative_to(_PPA_ROOT.parent).as_posix())
    return frozenset(found)


def test_every_real_model_call_site_is_accounted_for():
    """A new site with no entry in `_EXPECTED_SITES` — or a removed one
    still listed — fails here first, before it can ship uninstrumented."""

    actual = _modules_calling_client()
    assert actual == _EXPECTED_SITES, (
        f"missing from _EXPECTED_SITES: {actual - _EXPECTED_SITES}; "
        f"stale entries no longer true: {_EXPECTED_SITES - actual}"
    )


def test_every_real_model_call_site_declares_a_canonical_llm_surface():
    violations: list[str] = []
    for rel_path in sorted(_EXPECTED_SITES):
        module_name = rel_path[:-3].replace("/", ".")  # "ppa/agents/turn.py" -> "ppa.agents.turn"
        module = importlib.import_module(module_name)
        surface = getattr(module, "LLM_SURFACE", None)
        if not surface:
            violations.append(f"{rel_path}: no non-empty LLM_SURFACE declared")
            continue
        if not isinstance(surface, frozenset) or not surface <= LLM_SURFACES:
            violations.append(f"{rel_path}: LLM_SURFACE={surface!r} is not a subset of {sorted(LLM_SURFACES)}")

    assert not violations, violations


def test_llm_surfaces_is_exactly_the_four_named_in_design_doc_217():
    assert LLM_SURFACES == frozenset({"interpretation", "question_generation", "guidance", "narration"})
