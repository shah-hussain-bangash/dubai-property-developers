"""Invalid token counters cannot corrupt usage totals or model cost estimates."""

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.llm.router import ModelRouter, ModelTarget
from core.llm.types import ChatMessage, ChatRole, LLMRequest, LLMResponse
from core.observability.usage import InMemoryUsageTracker, ModelPrice, TokenUsage
from core.resilience.retry import RetryPolicy

INVALID_COUNTS = (-1, True, False, 1.0, 1.5, float("nan"), float("inf"), "2", None)


class TokenUsageValidationTests(unittest.IsolatedAsyncioTestCase):
    def test_usage_records_reject_negative_and_non_integer_counts(self):
        for field in ("input_tokens", "output_tokens"):
            for count in INVALID_COUNTS:
                with self.subTest(field=field, count=count):
                    with self.assertRaisesRegex(ValueError, "non-negative integers"):
                        TokenUsage(**{field: count})

    def test_model_responses_reject_invalid_counts_without_coercion(self):
        for field in ("input_tokens", "output_tokens"):
            for count in INVALID_COUNTS:
                with self.subTest(field=field, count=count):
                    with self.assertRaises(ValueError):
                        LLMResponse(
                            text="Fictional fixture answer",
                            provider="fixture",
                            model="fixture-model",
                            **{field: count},
                        )

    def test_valid_zero_and_large_counts_keep_aggregation_and_decimal_costs(self):
        self.assertEqual(TokenUsage().total_tokens, 0)
        usage = TokenUsage(10**12, 3) + TokenUsage(2, 4)
        self.assertEqual(usage, TokenUsage(10**12 + 2, 7))
        # Fictional test prices; no provider rates are assumed.
        tracker = InMemoryUsageTracker(
            prices={"fixture-model": ModelPrice(Decimal("2"), Decimal("3"))}
        )
        tracker.record(
            agent_id="fixture-agent", model="fixture-model", usage=usage, correlation_id=None
        )
        totals = tracker.totals()
        self.assertEqual(totals[("fixture-agent", "fixture-model")], usage)
        self.assertEqual(tracker.estimated_cost("fixture-model", usage), Decimal("2000000.000025"))
        self.assertEqual(tracker.estimated_cost("unpriced-fixture", usage), Decimal("0"))

    async def test_invalid_provider_counts_fall_back_without_entering_usage_totals(self):
        async def invalid_response(request, *, model):
            return LLMResponse(
                text="Fictional invalid answer",
                provider="invalid-fixture",
                model=model,
                input_tokens=-1,
            )

        invalid = SimpleNamespace(
            name="invalid-fixture", complete=AsyncMock(side_effect=invalid_response)
        )
        valid = SimpleNamespace(
            name="valid-fixture",
            complete=AsyncMock(
                return_value=LLMResponse(
                    text="Fictional valid answer",
                    provider="valid-fixture",
                    model="valid-model",
                    input_tokens=3,
                    output_tokens=2,
                )
            ),
        )
        tracker = InMemoryUsageTracker()
        router = ModelRouter(
            {"invalid": invalid, "valid": valid},
            [ModelTarget("invalid", "invalid-model"), ModelTarget("valid", "valid-model")],
            retry_policy=RetryPolicy(max_attempts=1),
            usage_sink=tracker,
        )

        response = await router.complete(
            LLMRequest(messages=[ChatMessage(role=ChatRole.USER, content="Fixture prompt")]),
            agent_id="fixture-agent",
        )

        self.assertEqual(response.provider, "valid-fixture")
        self.assertEqual(tracker.totals(), {("fixture-agent", "valid-model"): TokenUsage(3, 2)})
        invalid.complete.assert_awaited_once()
        valid.complete.assert_awaited_once()
