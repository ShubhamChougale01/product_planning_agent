"""Every tool speaks this language (DESIGN.md §2.12, S1.7).

`recommended_action` is the contract callers branch on. `is_retryable` is
advisory only — it answers exactly one question, "will sending this
identical request again likely succeed?" It must never be read as "give up"
when false; `recommended_action` says what to actually do.

Three legal states, not two:

- **Success with data** — `success=True, result_count=N`.
- **Success and empty** — `success=True, result_count=0`. A query that ran
  and found nothing is not a failure — never convert it to one, never retry
  it because it's empty.
- **Degraded success** — `success=True, degraded=True`. Ran without full
  capability (e.g. research with no web access). An honest caveat, not an
  error.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ppa.results.categories import CATEGORY_RULES, ErrorCategory, RecoveryAction


class ErrorInfo(BaseModel):
    """`recommended_action` has no default — omitting it is a construction
    error, not a silently-populated gap (DESIGN.md §2.12: "always
    populated")."""

    model_config = ConfigDict(extra="forbid")

    category: ErrorCategory
    code: str
    is_retryable: bool
    retry_after_ms: int | None = None
    description: str
    recommended_action: RecoveryAction
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _matches_the_fixed_category_mapping(self) -> "ErrorInfo":
        rule = CATEGORY_RULES[self.category]
        if self.is_retryable != rule["is_retryable"]:
            raise ValueError(
                f"{self.category.value} must have is_retryable={rule['is_retryable']}, "
                f"got {self.is_retryable}"
            )
        if self.recommended_action != rule["recommended_action"]:
            raise ValueError(
                f"{self.category.value} must have recommended_action="
                f"{rule['recommended_action'].value}, got {self.recommended_action.value}"
            )
        return self


class ToolResult(BaseModel):
    """The envelope every tool returns, always — never a bare string, never a
    raw exception."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    degraded: bool = False
    result_count: int = 0
    data: Any | None = None
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def _error_and_success_agree(self) -> "ToolResult":
        if self.success and self.error is not None:
            raise ValueError("success=True may not carry an error")
        if not self.success and self.error is None:
            raise ValueError("success=False must carry an error — recovery has nothing to branch on otherwise")
        return self
