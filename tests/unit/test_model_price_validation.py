"""Configured prices must support finite, non-negative decimal cost estimates."""

import unittest
from decimal import Decimal

from core.observability.usage import InMemoryUsageTracker, ModelPrice, TokenUsage


class ModelPriceValidationTests(unittest.TestCase):
    def test_negative_and_non_finite_prices_are_rejected_on_both_rates(self):
        invalid = (
            Decimal("-0.01"),
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
        )
        for field in ("input_per_million", "output_per_million"):
            for price in invalid:
                values = {"input_per_million": Decimal("0"), "output_per_million": Decimal("0")}
                values[field] = price
                with (
                    self.subTest(field=field, price=price),
                    self.assertRaisesRegex(ValueError, "finite non-negative Decimal"),
                ):
                    ModelPrice(**values)

    def test_non_decimal_prices_are_rejected_without_implicit_conversion(self):
        for field in ("input_per_million", "output_per_million"):
            for price in (None, True, False, 0, 2, 0.1, "0.1"):
                values = {"input_per_million": Decimal("0"), "output_per_million": Decimal("0")}
                values[field] = price
                with (
                    self.subTest(field=field, price=price),
                    self.assertRaisesRegex(ValueError, "finite non-negative Decimal"),
                ):
                    ModelPrice(**values)

    def test_valid_decimal_and_free_rates_keep_exact_cost_estimates(self):
        # These are fictional test rates, not provider prices.
        tracker = InMemoryUsageTracker(
            prices={
                "fixture-decimal": ModelPrice(Decimal("0.1"), Decimal("0.2")),
                "fixture-free": ModelPrice(Decimal("0"), Decimal("-0")),
                "fixture-input-only": ModelPrice(Decimal("1.5"), Decimal("0")),
            }
        )
        usage = TokenUsage(3, 7)

        self.assertEqual(tracker.estimated_cost("fixture-decimal", usage), Decimal("0.0000017"))
        self.assertEqual(tracker.estimated_cost("fixture-free", usage), Decimal("0"))
        self.assertEqual(tracker.estimated_cost("fixture-input-only", usage), Decimal("0.0000045"))
        self.assertEqual(tracker.estimated_cost("fixture-unpriced", usage), Decimal("0"))
        self.assertEqual(tracker.estimated_cost("fixture-decimal", TokenUsage()), Decimal("0"))
