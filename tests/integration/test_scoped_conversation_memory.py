"""PostgreSQL ownership filters and agent-state partitions on existing conversations."""

import asyncio
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.config.settings import get_settings
from core.exceptions.errors import AuthorizationError
from core.memory.base import MemoryMessage
from database.models.conversation import Conversation
from database.models.identity import Organization
from database.repositories.conversation_memory import (
    AGENT_FIELD,
    STATE_FIELD,
    SqlConversationMemory,
)
from database.sessions.engine import create_engine
from tests.factories import integration_enabled

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not integration_enabled(), reason="Set RUN_INTEGRATION_TESTS=1"),
]


@pytest.fixture
async def scoped_database():
    settings = get_settings()
    if not settings.is_dev_like:
        pytest.skip("Scoped memory checks require a development database")
    engine = create_engine(settings)
    organization, foreign, conversation = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                factory = async_sessionmaker(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                async with factory() as session, session.begin():
                    for owner in [organization, foreign]:
                        session.add(
                            Organization(
                                id=owner,
                                name="Fictional scoped memory",
                                slug="memory-" + owner.hex,
                                is_active=True,
                            )
                        )
                    await session.flush()
                    session.add(
                        Conversation(
                            id=conversation,
                            organization_id=organization,
                            channel="web_chat",
                            state={},
                        )
                    )
                yield (
                    SqlConversationMemory(factory, organization),
                    SqlConversationMemory(factory, foreign),
                    str(conversation),
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def test_database_history_keeps_agent_and_organization_boundaries(scoped_database):
    raw, foreign, conversation = scoped_database
    wa = raw.scoped(str(raw._org), "whatsapp")
    sales = raw.scoped(str(raw._org), "sales_conversation")
    await wa.append(
        conversation,
        MemoryMessage(
            role="customer",
            content="Fictional WhatsApp history",
            metadata={AGENT_FIELD: "sales_conversation"},
        ),
    )
    await sales.append(
        conversation, MemoryMessage(role="customer", content="Fictional sales history")
    )
    await raw.append(
        conversation,
        MemoryMessage(
            role="staff", content="Fictional unscoped history", metadata={AGENT_FIELD: "whatsapp"}
        ),
    )
    assert [m.content for m in await wa.history(conversation)] == ["Fictional WhatsApp history"]
    assert [m.content for m in await sales.history(conversation)] == ["Fictional sales history"]
    assert [m.content for m in await raw.history(conversation)] == ["Fictional unscoped history"]
    outsider = foreign.scoped(str(foreign._org), "whatsapp")
    assert await outsider.history(conversation) == []
    with pytest.raises(LookupError):
        await outsider.append(conversation, MemoryMessage(role="customer", content="Blocked"))


async def test_database_state_updates_preserve_other_agents_and_reject_forged_partition(
    scoped_database,
):
    raw, _, conversation = scoped_database
    wa = raw.scoped(str(raw._org), "whatsapp")
    sales = raw.scoped(str(raw._org), "sales_conversation")
    await wa.set_state(conversation, {"opted_out": True})
    await sales.set_state(conversation, {"marker": "sales-only"})
    assert await wa.get_state(conversation) == {"opted_out": True}
    assert await sales.get_state(conversation) == {"marker": "sales-only"}
    assert await raw.get_state(conversation) == {}
    await raw.set_state(
        conversation,
        {"operator_note": "Fictional", STATE_FIELD: {"whatsapp": {"opted_out": False}}},
    )
    assert await wa.get_state(conversation) == {"opted_out": True}
    assert await sales.get_state(conversation) == {"marker": "sales-only"}
    assert await raw.get_state(conversation) == {"operator_note": "Fictional"}


async def test_database_legacy_state_requires_ownership_review(scoped_database):
    raw, _, conversation = scoped_database
    await raw.set_state(conversation, {"opted_out": True})
    wa = raw.scoped(str(raw._org), "whatsapp")
    with pytest.raises(AuthorizationError, match="ownership review"):
        await wa.get_state(conversation)
    with pytest.raises(AuthorizationError, match="ownership review"):
        await wa.set_state(conversation, {})
    with pytest.raises(AuthorizationError, match="ownership review"):
        await wa.update_state(conversation, {"marker": "blocked"})
    assert await raw.get_state(conversation) == {"opted_out": True}


async def test_database_scope_cannot_rebind_to_another_owner(scoped_database):
    raw, foreign, _ = scoped_database
    for tenant in [str(foreign._org), "not-an-organization-id"]:
        with pytest.raises(AuthorizationError):
            raw.scoped(tenant, "whatsapp")
    wa = raw.scoped(str(raw._org), "whatsapp")
    with pytest.raises(AuthorizationError):
        wa.scoped(str(raw._org), "sales_conversation")


async def test_database_patch_preserves_optout_and_rejects_reserved_state_injection(
    scoped_database,
):
    raw, _, conversation = scoped_database
    wa = raw.scoped(str(raw._org), "whatsapp")
    sales = raw.scoped(str(raw._org), "sales_conversation")
    await wa.update_state(conversation, {"opted_out": True})
    await sales.update_state(conversation, {"marker": "sales-only"})
    result = await wa.update_state(conversation, {"last_inbound_at": "fictional-later-event"})
    assert result["opted_out"] is True
    await raw.update_state(
        conversation,
        {"operator_note": "Fictional", STATE_FIELD: {"whatsapp": {"opted_out": False}}},
    )
    assert (await wa.get_state(conversation))["opted_out"] is True
    assert await sales.get_state(conversation) == {"marker": "sales-only"}
    assert await raw.get_state(conversation) == {"operator_note": "Fictional"}


async def test_concurrent_database_patches_do_not_lose_fields_or_optout():
    settings = get_settings()
    if not settings.is_dev_like:
        pytest.skip("Concurrent memory checks require a development database")
    engine = create_engine(settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    organization, conversation = uuid.uuid4(), uuid.uuid4()
    tasks = []
    try:
        # Separate connections need committed, exclusively owned fictional fixtures.
        async with factory() as session, session.begin():
            session.add(
                Organization(
                    id=organization,
                    name="Fictional concurrent memory",
                    slug="memory-" + organization.hex,
                    is_active=True,
                )
            )
            await session.flush()
            session.add(
                Conversation(
                    id=conversation,
                    organization_id=organization,
                    channel="whatsapp",
                    state={},
                )
            )
        raw = SqlConversationMemory(factory, organization)
        wa = raw.scoped(str(organization), "whatsapp")
        sales = raw.scoped(str(organization), "sales_conversation")
        await wa.update_state(str(conversation), {"opted_out": True})
        await sales.update_state(str(conversation), {"marker": "sales-only"})
        tasks = [
            asyncio.create_task(wa.update_state(str(conversation), {f"event_{i}": i}))
            for i in range(8)
        ]
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        assert await wa.get_state(str(conversation)) == {
            "opted_out": True,
            **{f"event_{i}": i for i in range(8)},
        }
        assert await sales.get_state(str(conversation)) == {"marker": "sales-only"}
    finally:
        for pending in tasks:
            if not pending.done():
                pending.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            async with factory() as session, session.begin():
                await session.execute(
                    delete(Conversation).where(
                        Conversation.id == conversation,
                        Conversation.organization_id == organization,
                    )
                )
                await session.execute(delete(Organization).where(Organization.id == organization))
        finally:
            await engine.dispose()
