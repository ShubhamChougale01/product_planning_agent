"""The ModelProvider seam — the only place in the codebase that names a model
or touches a credential.

Two rules, and every other module depends on them holding:

1. **No model string lives outside this file.** Switching from Sonnet to Opus, or
   dropping the eval loop onto Haiku, is a config change. Agent logic never sees a
   model id.
2. **Credentials are resolved at call time and never persist.** They come from the
   environment or the OS keychain when a client is built, and are not stored on the
   instance, written to the ledger, placed in a prompt, or logged (DESIGN.md §2.19.1).

Auth defaults to ``subscription``: the Agent SDK spawns the Claude Code CLI and
inherits its login, so no API key is involved at all. Verified 2026-09-23 —
see ``docs/decisions/auth.md``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# The only model strings in the codebase.
# ---------------------------------------------------------------------------

#: Named tiers, so callers ask for a *capability level* rather than a model.
#: ``deep`` is for the question engine when quality matters most; ``cheap`` exists
#: for eval loops (T34, open decision #2) where run count beats per-run quality.
MODEL_TIERS: dict[str, str] = {
    "primary": "claude-sonnet-5",
    "deep": "claude-opus-5",
    "cheap": "claude-haiku-4-5-20251001",
}

DEFAULT_TIER = "primary"

AuthSource = Literal["subscription", "api_key"]


class ModelConfig(BaseModel):
    """How to reach a model. Loaded from ``config/model.yaml``, overridable by env."""

    tier: str = Field(default=DEFAULT_TIER, description="A key of MODEL_TIERS.")
    model_override: str | None = Field(
        default=None,
        description="Explicit model id, bypassing the tier. For pinning during an experiment.",
    )
    auth_source: AuthSource = Field(
        default="subscription",
        description="'subscription' inherits the Claude Code CLI login; 'api_key' reads a key.",
    )
    api_key_env: str = Field(
        default="ANTHROPIC_API_KEY",
        description="Env var holding the key when auth_source is 'api_key'. Never the key itself.",
    )
    keychain_service: str | None = Field(
        default=None,
        description="Optional OS keychain service name, tried when the env var is absent.",
    )
    keychain_account: str | None = None
    max_turns: int = Field(default=30, ge=1)
    permission_mode: str = Field(default="default")

    def resolved_model(self) -> str:
        """The model id this config points at."""
        if self.model_override:
            return self.model_override
        try:
            return MODEL_TIERS[self.tier]
        except KeyError:
            raise ValueError(
                f"Unknown model tier {self.tier!r}. Known tiers: {sorted(MODEL_TIERS)}"
            ) from None


class ModelProvider:
    """Builds configured SDK clients. Nothing else constructs a ``ClaudeSDKClient``."""

    def __init__(self, cfg: ModelConfig | None = None) -> None:
        self.cfg = cfg or ModelConfig()
        # Validate eagerly so a bad tier fails at startup, not mid-conversation.
        self.model = self.cfg.resolved_model()

    # -- construction -------------------------------------------------------

    @classmethod
    def from_config(cls, path: str | Path | None = None) -> ModelProvider:
        """Load ``config/model.yaml`` if present, then apply environment overrides.

        Env wins over file, file wins over the defaults above:

        * ``PPA_MODEL_TIER``     — primary | deep | cheap
        * ``PPA_MODEL``          — explicit model id, bypassing the tier
        * ``PPA_AUTH_SOURCE``    — subscription | api_key
        * ``PPA_MAX_TURNS``      — integer
        """
        data: dict[str, Any] = {}
        if path is not None:
            p = Path(path)
            if p.exists():
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

        if tier := os.environ.get("PPA_MODEL_TIER"):
            data["tier"] = tier
        if override := os.environ.get("PPA_MODEL"):
            data["model_override"] = override
        if auth := os.environ.get("PPA_AUTH_SOURCE"):
            data["auth_source"] = auth
        if turns := os.environ.get("PPA_MAX_TURNS"):
            data["max_turns"] = int(turns)

        return cls(ModelConfig(**data))

    # -- credentials --------------------------------------------------------

    def _credential(self) -> str | None:
        """Resolve a credential *now*. The return value is never stored on ``self``.

        Returns ``None`` under subscription auth, which is the point: there is no
        credential to leak because there is no credential.
        """
        if self.cfg.auth_source == "subscription":
            return None

        if value := os.environ.get(self.cfg.api_key_env):
            return value

        if self.cfg.keychain_service and self.cfg.keychain_account:
            try:
                import keyring  # optional; not a declared dependency
            except ImportError:
                pass
            else:
                if value := keyring.get_password(
                    self.cfg.keychain_service, self.cfg.keychain_account
                ):
                    return value

        raise RuntimeError(
            f"auth_source is 'api_key' but no credential was found in "
            f"${self.cfg.api_key_env} or the OS keychain. "
            f"Set the environment variable, or switch auth_source to 'subscription'."
        )

    # -- clients ------------------------------------------------------------

    def options(
        self,
        *,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int | None = None,
        **extra: Any,
    ) -> ClaudeAgentOptions:
        """Build SDK options for one agent invocation.

        ``allowed_tools`` is the agent's registry grant. It is a hint to the model,
        not a security boundary — the grant is enforced again at dispatch (§2.18).
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "allowed_tools": allowed_tools or [],
            "max_turns": max_turns or self.cfg.max_turns,
            "permission_mode": self.cfg.permission_mode,
        }
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt
        kwargs.update(extra)
        return ClaudeAgentOptions(**kwargs)

    def client(self, **kwargs: Any) -> ClaudeSDKClient:
        """A client for one agent invocation.

        Credentials are resolved here, at call time, and handed to the transport
        without ever being held on this object.
        """
        credential = self._credential()
        options = self.options(**kwargs)
        if credential is not None:
            env = dict(getattr(options, "env", None) or {})
            env[self.cfg.api_key_env] = credential
            options.env = env
        return ClaudeSDKClient(options=options)

    def describe(self) -> dict[str, Any]:
        """Safe-to-log summary. Deliberately contains no credential value."""
        return {
            "model": self.model,
            "tier": self.cfg.tier,
            "auth_source": self.cfg.auth_source,
            "credential_source": (
                "claude-code-cli-login"
                if self.cfg.auth_source == "subscription"
                else f"${self.cfg.api_key_env}"
            ),
            "max_turns": self.cfg.max_turns,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"ModelProvider(model={self.model!r}, auth={self.cfg.auth_source!r})"
