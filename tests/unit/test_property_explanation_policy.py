"""Availability contract regression cases; no network or project .env reads."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
from core.llm.property_explanation_policy import AVAILABILITY_WARNING as W
from core.llm.property_explanation_policy import accepts_availability_wording as accepts


class Wording(unittest.TestCase):
    def test_cautious_explanation_accepted(self):
        self.assertTrue(accepts("Fictional apartment [P1]. " + W))

    def test_screenshot_claim_rejected(self):
        self.assertFalse(accepts("Availability is confirmed [P1]. " + W))

    def test_historical_available_label_cannot_become_claim(self):
        self.assertFalse(accepts("The unit is available [P1]. " + W))

    def test_warning_missing_rejected(self):
        self.assertFalse(accepts("Fictional apartment [P1]."))

    def test_conflicting_claim_not_fixed_by_disclaimer(self):
        self.assertFalse(accepts(W + " All properties are verified."))

    def test_developer_confirmation_claim_rejected(self):
        self.assertFalse(accepts("The developer has confirmed the listing [P1]. " + W))

    def test_booking_claim_rejected(self):
        self.assertFalse(accepts("Ready to book [P1]. " + W))

    def test_stock_claim_rejected(self):
        self.assertFalse(accepts("In stock now [P1]. " + W))

    def test_sold_or_reserved_claim_rejected(self):
        for word in ["sold", "reserved"]:
            self.assertFalse(accepts("Unit is " + word + " [P1]. " + W))

    def test_zero_width_and_fullwidth_words_checked(self):
        for text in ["Avail\u200bability is confirmed.", "\uff21vailability is confirmed."]:
            self.assertFalse(accepts(text + " " + W))

    def test_markdown_and_multiline_claim_checked(self):
        self.assertFalse(accepts("**Availability** is\nconfirmed [P1]. " + W))

    def test_price_uncertainty_and_no_return_guarantee_allowed(self):
        self.assertTrue(
            accepts("Price is unconfirmed [P1]. No investment return is guaranteed. " + W)
        )

    def test_payment_plan_option_does_not_override_stock_check(self):
        self.assertTrue(accepts("Payment plan options are available [P1]. " + W))
        self.assertFalse(
            accepts("Payment plan options are available. Units are available [P1]. " + W)
        )

    def test_duplicate_warning_rejected(self):
        self.assertFalse(accepts(W + " " + W))

    def test_blank_or_nontext_rejected(self):
        for value in ["", None, 42]:
            self.assertFalse(accepts(value))


if __name__ == "__main__":
    unittest.main()
