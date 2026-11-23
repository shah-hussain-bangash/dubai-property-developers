"""Token usage and cost tracking interfaces.

Prices are *configuration*, not facts baked into code: the default price table is
empty, so costs report as zero until an operator configures real contract prices.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        for count in (self.input_tokens, self.output_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("token counts must be non-negative integers")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_million: Decimal
    output_per_million: Decimal


class UsageSink(Protocol):
    def record(
        self, *, agent_id: str, model: str, usage: TokenUsage, correlation_id: str | None
    ) -> None: ...


@dataclass
class InMemoryUsageTracker:
    """Aggregates usage per (agent, model). Swap for a DB/metrics sink in production."""

    prices: dict[str, ModelPrice] = field(default_factory=dict)
    _totals: dict[tuple[str, str], TokenUsage] = field(
        default_factory=lambda: defaultdict(TokenUsage)
    )

    def record(
        self, *, agent_id: str, model: str, usage: TokenUsage, correlation_id: str | None
    ) -> None:
        self._totals[(agent_id, model)] = self._totals[(agent_id, model)] + usage

    def totals(self) -> dict[tuple[str, str], TokenUsage]:
        return dict(self._totals)

    def estimated_cost(self, model: str, usage: TokenUsage) -> Decimal:
        price = self.prices.get(model)
        if price is None:
            return Decimal("0")
        million = Decimal(1_000_000)
        return (
            Decimal(usage.input_tokens) * price.input_per_million / million
            + Decimal(usage.output_tokens) * price.output_per_million / million
        )
