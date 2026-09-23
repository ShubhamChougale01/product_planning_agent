"""The two T01 grep gates, as tests.

They were checked by hand once. Encoding them means they stay true for the next
34 tasks instead of quietly rotting the first time someone pastes a model id into
an agent prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "projects", "node_modules"}

MODEL_SEAM = REPO / "ppa" / "providers" / "model.py"

# A model id, in any of the shapes Anthropic ships.
MODEL_ID = re.compile(r"claude-(?:opus|sonnet|haiku|fable)[-\w.]*")

# A credential *value*, not the word "api_key". The distinction matters: env var
# names are fine and unavoidable; a 16+ char literal assigned to one is not.
CREDENTIAL_VALUE = re.compile(
    r"""(?:
          sk-ant-[A-Za-z0-9_-]{8,}
        | (?:api[_-]?key|token|secret|password)\s*[:=]\s*["'][A-Za-z0-9_\-]{16,}["']
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _source_files(*suffixes: str) -> list[Path]:
    out = []
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if SKIP_DIRS & set(path.relative_to(REPO).parts):
            continue
        out.append(path)
    return out


def test_model_strings_live_only_in_the_seam():
    """Switching model must be a config change, not a find-and-replace.

    Tier names (`primary`, `deep`, `cheap`) are allowed anywhere. An actual
    model id is not — not in Python, and not in a config file either. A
    `model_override: claude-opus-5` slipped into `config/model.yaml` would
    defeat the seam exactly as badly as hard-coding it in a function, so
    config and code formats are scanned together here.

    `.md` is deliberately NOT scanned: a decision record documenting which
    model id was actually verified (docs/decisions/*.md, a completed task's
    build record quoting `ppa doctor` output) is evidence, not configuration
    — it doesn't drive runtime behavior, so it isn't a seam violation. The
    credential-value check below still covers `.md`, because a leaked secret
    is equally bad wherever it appears; a model id is not equally bad
    everywhere, only where it configures something.
    """
    offenders = {}
    for path in _source_files(".py", ".yaml", ".yml", ".toml", ".json"):
        # This test file's own docstring names an example id; it isn't a seam
        # violation, it's the sentence explaining why one would be.
        if path in (MODEL_SEAM, Path(__file__)):
            continue
        if hits := MODEL_ID.findall(path.read_text(encoding="utf-8")):
            offenders[str(path.relative_to(REPO))] = sorted(set(hits))

    assert not offenders, (
        "Model ids found outside ppa/providers/model.py. Ask ModelProvider for a "
        f"tier instead of naming a model: {offenders}"
    )


def test_no_credential_values_are_committed():
    """Env var *names* are fine. Values are not (DESIGN.md 2.19.1)."""
    offenders = []
    for path in _source_files(".py", ".yaml", ".yml", ".toml", ".md", ".json", ".txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        # This test file necessarily contains the patterns it looks for.
        if path == Path(__file__):
            continue
        if CREDENTIAL_VALUE.search(text):
            offenders.append(str(path.relative_to(REPO)))

    assert not offenders, f"Possible credential values committed: {offenders}"


def test_gitignore_excludes_env_and_project_ledgers():
    """Local-by-default is a mitigation, so it needs to actually be configured."""
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "projects/", ".venv/", "*.local.*", "scratch/"):
        assert pattern in ignored, f"{pattern!r} missing from .gitignore"


@pytest.mark.parametrize("tier", ["primary", "deep", "cheap"])
def test_every_tier_resolves(tier):
    from ppa.providers.model import ModelConfig

    assert ModelConfig(tier=tier).resolved_model()
