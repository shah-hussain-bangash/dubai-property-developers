"""Role collections cannot mutate an existing actor's permissions."""

import unittest

from core.security.rbac import Permission, Principal, Role


class PrincipalRoleSnapshotTests(unittest.TestCase):
    def test_adding_a_role_does_not_elevate_an_existing_principal(self):
        roles = {Role.VIEWER}
        principal = Principal(subject="fixture-viewer", tenant_id="fixture", roles=roles)
        roles.add(Role.ADMIN)

        self.assertFalse(principal.has(Permission.SETTINGS_ADMIN))
        self.assertIsInstance(principal.roles, frozenset)
        later = Principal(subject="fixture-admin", tenant_id="fixture", roles=roles)
        self.assertTrue(later.has(Permission.SETTINGS_ADMIN))

    def test_clearing_input_roles_keeps_existing_permissions(self):
        roles = {Role.SALES_MANAGER}
        principal = Principal(subject="fixture-manager", tenant_id="fixture", roles=roles)
        roles.clear()

        self.assertTrue(principal.has(Permission.MESSAGES_SEND))
        self.assertEqual(principal.roles, frozenset({Role.SALES_MANAGER}))

    def test_default_and_frozen_roles_keep_existing_behavior(self):
        empty = Principal(subject="fixture-empty", tenant_id="fixture")
        viewer = Principal(
            subject="fixture-viewer", tenant_id="fixture", roles=frozenset({Role.VIEWER})
        )

        self.assertEqual(empty.permissions, frozenset())
        self.assertTrue(viewer.has(Permission.LEADS_READ))
        self.assertFalse(viewer.has(Permission.SETTINGS_ADMIN))
