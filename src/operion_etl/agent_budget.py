"""Content-free diagnostics captured at the SDK's budget enforcement boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits

BudgetKind = Literal[
    "model_requests", "tool_calls", "input_tokens", "output_tokens", "deadline"
]


@dataclass(frozen=True)
class BudgetExceeded:
    kind: BudgetKind
    used: int | float
    limit: int | float
    attempted: int | None = None


@dataclass
class DiagnosedUsageLimits(UsageLimits):
    """Keep SDK enforcement and retain its numeric cause before UI sanitization.

    Pass ``usage`` to the agent as well. Streaming checks can see provider-reported
    tokens before they are committed to RunUsage, so retain their high-water marks.
    These are observed usage, not an estimate of unreported/cancelled generation.
    """

    usage: RunUsage = field(default_factory=RunUsage)
    exceeded: BudgetExceeded | None = field(default=None, init=False)
    _input_tokens: int = field(default=0, init=False)
    _output_tokens: int = field(default=0, init=False)

    def _observe(self, usage: RunUsage) -> None:
        self._input_tokens = max(self._input_tokens, usage.input_tokens)
        self._output_tokens = max(self._output_tokens, usage.output_tokens)

    def check_before_request(self, usage: RunUsage) -> None:
        self._observe(usage)
        try:
            super().check_before_request(usage)
        except UsageLimitExceeded:
            if self.request_limit is not None and usage.requests >= self.request_limit:
                self.exceeded = BudgetExceeded(
                    "model_requests",
                    usage.requests,
                    self.request_limit,
                    usage.requests + 1,
                )
            elif (
                self.input_tokens_limit is not None
                and usage.input_tokens > self.input_tokens_limit
            ):
                self.exceeded = BudgetExceeded(
                    "input_tokens", usage.input_tokens, self.input_tokens_limit
                )
            raise

    def check_tokens(self, usage: RunUsage) -> None:
        self._observe(usage)
        try:
            super().check_tokens(usage)
        except UsageLimitExceeded:
            if (
                self.input_tokens_limit is not None
                and usage.input_tokens > self.input_tokens_limit
            ):
                self.exceeded = BudgetExceeded(
                    "input_tokens", usage.input_tokens, self.input_tokens_limit
                )
            elif (
                self.output_tokens_limit is not None
                and usage.output_tokens > self.output_tokens_limit
            ):
                self.exceeded = BudgetExceeded(
                    "output_tokens", usage.output_tokens, self.output_tokens_limit
                )
            raise

    def check_before_tool_call(self, projected_usage: RunUsage) -> None:
        try:
            super().check_before_tool_call(projected_usage)
        except UsageLimitExceeded:
            if self.tool_calls_limit is not None:
                self.exceeded = BudgetExceeded(
                    "tool_calls",
                    self.usage.tool_calls,
                    self.tool_calls_limit,
                    projected_usage.tool_calls,
                )
            raise

    def record_deadline(self, elapsed: float, limit: float) -> None:
        self.exceeded = BudgetExceeded("deadline", elapsed, limit)

    def snapshot(self, elapsed: float, timeout: float) -> dict[str, Any]:
        self._observe(self.usage)
        return {
            "version": 1,
            "usage": {
                "model_requests": self.usage.requests,
                "tool_calls": self.usage.tool_calls,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "elapsed_seconds": round(elapsed, 6),
            },
            "limits": {
                "model_requests": self.request_limit,
                "tool_calls": self.tool_calls_limit,
                "input_tokens": self.input_tokens_limit,
                "output_tokens": self.output_tokens_limit,
                "deadline_seconds": timeout,
            },
            "exceeded": asdict(self.exceeded) if self.exceeded else None,
        }
