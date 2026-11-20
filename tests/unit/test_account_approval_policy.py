"""Standalone policy tests; do not load application or pytest fixtures."""

import json
import runpy
import unittest
from dataclasses import replace
from pathlib import Path

namespace = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "core/security/account_approval.py")
)
AccountAccess = namespace["AccountAccess"]
AccountStatus = namespace["AccountStatus"]
decide_account = namespace["decide_account"]
can_access_dashboard = namespace["can_access_dashboard"]


class AccountApprovalTests(unittest.TestCase):
    def setUp(self):
        self.owner = AccountAccess("synthetic-owner", "synthetic-org", AccountStatus.APPROVED)
        self.user = AccountAccess("synthetic-user", "synthetic-org")

    def decide(self, target=None, actor=None, **changes):
        arguments = {
            "actor": self.owner if actor is None else actor,
            "configured_owner_subject": "synthetic-owner",
            "organization_is_active": True,
            "approve": True,
        }
        arguments.update(changes)
        return decide_account(self.user if target is None else target, **arguments)

    def access(self, account, **changes):
        arguments = {
            "authenticated_subject": account.subject,
            "authenticated_organization_id": account.organization_id,
            "organization_is_active": True,
        }
        arguments.update(changes)
        return can_access_dashboard(account, **arguments)

    def test_registration_defaults_pending(self):
        self.assertIs(self.user.status, AccountStatus.PENDING)
        self.assertFalse(self.access(self.user))

    def test_owner_approval_enables_own_dashboard(self):
        approved = self.decide()
        self.assertTrue(self.access(approved))
        self.assertEqual(approved.decided_by, self.owner.subject)
        self.assertIsNotNone(approved.decided_at.tzinfo)
        self.assertIs(self.user.status, AccountStatus.PENDING)

    def test_rejection_denies_dashboard(self):
        rejected = self.decide(approve=False)
        self.assertIs(rejected.status, AccountStatus.REJECTED)
        self.assertFalse(self.access(rejected))

    def test_non_owner_cannot_decide(self):
        other = AccountAccess("synthetic-admin", "synthetic-org", AccountStatus.APPROVED)
        with self.assertRaises(PermissionError):
            self.decide(actor=other)

    def test_owner_must_be_approved_and_active(self):
        for actor in (
            replace(self.owner, status=AccountStatus.PENDING),
            replace(self.owner, is_active=False),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.decide(actor=actor)

    def test_cross_organization_decision_denied(self):
        with self.assertRaises(PermissionError):
            self.decide(target=replace(self.user, organization_id="other-org"))

    def test_self_approval_denied(self):
        with self.assertRaises(PermissionError):
            self.decide(target=self.owner)

    def test_completed_decision_cannot_be_overwritten(self):
        for status in (AccountStatus.APPROVED, AccountStatus.REJECTED):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.decide(target=replace(self.user, status=status))

    def test_inactive_account_or_organization_denied(self):
        with self.assertRaises(PermissionError):
            self.decide(target=replace(self.user, is_active=False))
        with self.assertRaises(PermissionError):
            self.decide(organization_is_active=False)
        approved = self.decide()
        self.assertFalse(self.access(replace(approved, is_active=False)))
        self.assertFalse(self.access(approved, organization_is_active=False))

    def test_another_users_dashboard_denied(self):
        approved = self.decide()
        self.assertFalse(self.access(approved, authenticated_subject="different-user"))

    def test_another_organizations_dashboard_denied(self):
        self.assertFalse(self.access(self.decide(), authenticated_organization_id="different-org"))

    def test_invalid_status_or_decision_rejected(self):
        with self.assertRaises(ValueError):
            AccountAccess("user", "org", status="approved")
        with self.assertRaises(ValueError):
            self.decide(approve="yes")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AccountApprovalTests)
    )
    print(
        json.dumps(
            {
                "tests_run": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                "successful": result.wasSuccessful(),
            }
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
