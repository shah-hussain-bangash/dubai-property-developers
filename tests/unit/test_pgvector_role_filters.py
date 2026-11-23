"""Restricted-role predicates apply before PostgreSQL candidate selection."""

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from knowledge.documents.models import AccessLevel
from knowledge.vectorstores.base import RetrievalFilter
from knowledge.vectorstores.pgvector import PgVectorStore


class PostgreSQLRoleFilterTests(unittest.IsolatedAsyncioTestCase):
    async def query_for(self, roles):
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        store = PgVectorStore(factory, uuid.uuid4(), "fixture-model")
        await store.search(
            [1.0, 0.0],
            k=1,
            filters=RetrievalFilter(
                tenant_id="tenant-a", access_levels=set(AccessLevel), principal_roles=roles
            ),
        )
        return session.execute.await_args.args[0].compile(dialect=postgresql.dialect())

    async def test_no_roles_excludes_restricted_documents_in_sql(self):
        compiled = await self.query_for(set())
        self.assertIn("knowledge_documents.access_level !=", str(compiled))
        self.assertIn("restricted", compiled.params.values())
        self.assertNotIn("@>", str(compiled))

    async def test_matching_role_can_admit_restricted_documents(self):
        compiled = await self.query_for({"manager"})
        self.assertIn("knowledge_documents.access_level !=", str(compiled))
        self.assertIn(" OR ", str(compiled))
        self.assertIn("@>", str(compiled))
        self.assertIn(["manager"], compiled.params.values())

    async def test_multiple_roles_allow_any_match(self):
        compiled = await self.query_for({"staff", "manager"})
        self.assertEqual(str(compiled).count("@>"), 2)
        self.assertIn(["manager"], compiled.params.values())
        self.assertIn(["staff"], compiled.params.values())

    async def test_role_values_remain_bound_parameters(self):
        role = "fictional'role"
        compiled = await self.query_for({role})
        self.assertNotIn(role, str(compiled))
        self.assertIn([role], compiled.params.values())
