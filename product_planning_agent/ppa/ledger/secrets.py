"""Inbound secret scanning and redaction (DESIGN.md §2.19.1, S2.1b).

Called on every free-text field **before** an `Event` is constructed
(`ppa/ledger/store.py::append_event`). The log is append-only — there is no
unwriting a credential once it's on disk, so this is the one place to catch
it, and it must run on the way in, always.

A hit is replaced with `[REDACTED:credential]`. The raw matched text is never
returned, never stored on `Finding`, never logged — it exists only inside
this module's own regex match objects, for the duration of one function call.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

REDACTED = "[REDACTED:credential]"

Family = Literal["api_key", "credentialed_uri", "private_key", "auth_header", "env_assignment"]


class Finding(BaseModel):
    """One redaction made. Deliberately carries no positional or textual
    detail beyond which pattern family fired — anything more specific risks
    reconstructing the very value this module exists to keep off the log."""

    model_config = ConfigDict(extra="forbid")

    family: Family


# --- API key shapes -------------------------------------------------------
# sk-... (Anthropic/OpenAI-style), ghp_... (GitHub), AKIA... (AWS access key
# id), plus a generic high-entropy run for shapes not covered by a prefix.
_SK_PREFIXED = re.compile(r"\bsk-[A-Za-z0-9_-]{10,}")
_GITHUB_TOKEN = re.compile(r"\bghp_[A-Za-z0-9]{20,}")
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_HIGH_ENTROPY_RUN = re.compile(r"\b[A-Za-z0-9+/_=-]{32,}\b")
_HIGH_ENTROPY_THRESHOLD = 3.5  # bits/char — a repeated or near-constant run scores near 0

# --- credentialed URIs -----------------------------------------------------
_CREDENTIALED_URI = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mongodb|redis)://[^\s:/@]+:[^\s@]+@\S+", re.IGNORECASE
)

# --- private key headers ----------------------------------------------------
_PRIVATE_KEY_HEADER = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")

# --- Authorization / Bearer headers ----------------------------------------
_AUTH_HEADER = re.compile(
    r"(?:\bAuthorization:\s*(?:Bearer\s+)?\S+)|(?:\bBearer\s+[A-Za-z0-9._-]{8,})",
    re.IGNORECASE,
)

# --- .env-style assignments -------------------------------------------------
_ENV_ASSIGNMENT = re.compile(
    r"\b(?:[A-Z][A-Z0-9]*_)?(?:PASSWORD|SECRET|TOKEN)\s*=\s*\S+", re.IGNORECASE
)


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    length = len(s)
    counts = Counter(s)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def scan_and_redact(text: str) -> tuple[str, list[Finding]]:
    """Return `(redacted_text, findings)`. Order matters only in that a more
    specific pattern (a GitHub token, say) is redacted before the generic
    high-entropy catch-all runs, so it isn't double-counted as a second,
    less-informative finding."""

    findings: list[Finding] = []

    def _redact(pattern: re.Pattern[str], family: Family, s: str) -> str:
        def _replace(_match: re.Match[str]) -> str:
            findings.append(Finding(family=family))
            return REDACTED

        return pattern.sub(_replace, s)

    result = text
    result = _redact(_PRIVATE_KEY_HEADER, "private_key", result)
    result = _redact(_CREDENTIALED_URI, "credentialed_uri", result)
    result = _redact(_AUTH_HEADER, "auth_header", result)
    result = _redact(_ENV_ASSIGNMENT, "env_assignment", result)
    result = _redact(_SK_PREFIXED, "api_key", result)
    result = _redact(_GITHUB_TOKEN, "api_key", result)
    result = _redact(_AWS_ACCESS_KEY, "api_key", result)

    def _replace_high_entropy(match: re.Match[str]) -> str:
        token = match.group(0)
        if _shannon_entropy(token) >= _HIGH_ENTROPY_THRESHOLD:
            findings.append(Finding(family="api_key"))
            return REDACTED
        return token

    result = _HIGH_ENTROPY_RUN.sub(_replace_high_entropy, result)

    return result, findings
