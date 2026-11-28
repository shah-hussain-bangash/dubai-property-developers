"""Durable memory must retain ownership and opt-outs across runtime restarts."""

import asyncio
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest

from core.exceptions.errors import AuthorizationError, PolicyViolationError
from core.memory.base import InMemoryConversationMemory, MemoryMessage
from database.repositories.sqlite_conversation_memory import SqliteConversationMemory
from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_agent_memory_isolation import other_organization, whatsapp
from tools.base import ToolCallContext
from workflows.runtime import build_runtime


def test_sqlite_memory_alias_cannot_enable_ephemeral_storage():
    with pytest.raises(ValueError, match="file path"):
        SqliteConversationMemory(":memory:")


@pytest.mark.parametrize("agent", dataset_ids())
async def test_restart_retains_only_the_owned_scope(tmp_path, agent):
    path = str(tmp_path / "memory.sqlite3")
    first = SqliteConversationMemory(path)
    for tenant in ["fictional-a", "fictional-b"]:
        for owner in dataset_ids():
            scope = first.scoped(tenant, owner)
            marker = f"Fictional {tenant}/{owner}"
            await scope.append("same-id", MemoryMessage(role="customer", content=marker))
            await scope.set_state("same-id", {"marker": marker})
    scope = SqliteConversationMemory(path).scoped("fictional-a", agent)
    expected = f"Fictional fictional-a/{agent}"
    assert [m.content for m in await scope.history("same-id")] == [expected]
    assert await scope.get_state("same-id") == {"marker": expected}
    assert await scope.history("other-id") == []
    assert await first.history("same-id") == []
    with pytest.raises(AuthorizationError):
        scope.scoped("fictional-b", agent)


async def test_durable_reads_and_writes_are_detached_snapshots(tmp_path):
    memory = SqliteConversationMemory(str(tmp_path / "memory.sqlite3"))
    message = MemoryMessage(role="staff", content="Fictional note", metadata={"nested": {"n": 1}})
    state = {"nested": {"n": 1}}
    await memory.append("fixture", message)
    await memory.set_state("fixture", state)
    message.metadata["nested"]["n"] = 99
    state["nested"]["n"] = 99
    history = await memory.history("fixture")
    history[0].metadata["nested"]["n"] = 77
    read = await memory.get_state("fixture")
    read["nested"]["n"] = 77
    assert (await memory.history("fixture"))[0].metadata == {"nested": {"n": 1}}
    assert await memory.get_state("fixture") == {"nested": {"n": 1}}


async def test_concurrent_independent_adapters_preserve_opt_out_and_all_patches(tmp_path):
    path = str(tmp_path / "memory.sqlite3")
    first, second = SqliteConversationMemory(path), SqliteConversationMemory(path)
    await first.set_state("fixture", {"opted_out": True})
    await asyncio.gather(
        *[(first if n % 2 else second).update_state("fixture", {f"field{n}": n}) for n in range(30)]
    )
    result = await first.get_state("fixture")
    assert result == {"opted_out": True, **{f"field{n}": n for n in range(30)}}


async def test_another_process_can_patch_the_same_persisted_state(tmp_path):
    path = str(tmp_path / "memory.sqlite3")
    memory = SqliteConversationMemory(path).scoped("fictional-a", "whatsapp")
    await memory.set_state("fixture", {"opted_out": True})
    code = (
        "import asyncio,sys; "
        "from database.repositories.sqlite_conversation_memory import SqliteConversationMemory; "
        "asyncio.run(SqliteConversationMemory(sys.argv[1]).scoped('fictional-a','whatsapp')"
        ".update_state('fixture',{'received':True}))"
    )
    result = await asyncio.to_thread(
        subprocess.run, [sys.executable, "-c", code, path], capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stderr.decode()
    assert await memory.get_state("fixture") == {"opted_out": True, "received": True}


async def test_history_limit_and_append_order_are_preserved(tmp_path):
    memory = SqliteConversationMemory(str(tmp_path / "memory.sqlite3"))
    now = datetime.now(UTC)
    for n in range(3):
        await memory.append(
            "fixture",
            MemoryMessage(role="customer", content=str(n), created_at=now - timedelta(days=n)),
        )
    assert [m.content for m in await memory.history("fixture", limit=2)] == ["1", "2"]
    assert await memory.history("fixture", limit=0) == []


@pytest.mark.parametrize("limit", [-1, True, 1.5])
async def test_invalid_history_limit_does_not_open_storage(tmp_path, limit):
    memory = SqliteConversationMemory(str(tmp_path / "memory.sqlite3"))
    with pytest.raises(ValueError):
        await memory.history("fixture", limit=limit)
    assert not memory.path.exists()


@pytest.mark.parametrize("raw", ["invalid json", "[]"])
async def test_corrupt_state_is_not_reset_or_replaced(tmp_path, raw):
    memory = SqliteConversationMemory(str(tmp_path / "memory.sqlite3"))
    await memory.set_state("fixture", {"opted_out": True})
    with closing(sqlite3.connect(memory.path)) as db, db:
        db.execute("UPDATE memory_states SET state=?", (raw,))
    with pytest.raises(ValueError):
        await memory.get_state("fixture")
    with pytest.raises(ValueError):
        await memory.update_state("fixture", {"received": True})
    with closing(sqlite3.connect(memory.path)) as db:
        assert db.execute("SELECT state FROM memory_states").fetchone()[0] == raw


async def test_non_json_state_does_not_replace_prior_consent(tmp_path):
    memory = SqliteConversationMemory(str(tmp_path / "memory.sqlite3"))
    await memory.set_state("fixture", {"opted_out": True})
    with pytest.raises(ValueError):
        await memory.update_state("fixture", {"unsupported": float("nan")})
    assert await memory.get_state("fixture") == {"opted_out": True}


async def test_configured_runtime_preserves_opt_out_and_blocks_approved_send(
    settings, ctx, manager, tmp_path
):
    settings.agent_memory_path = str(tmp_path / "memory.sqlite3")
    first = build_runtime(settings)
    await first.initialize()
    try:
        stopped = await first.agents.get("whatsapp").run(whatsapp("Please unsubscribe"), ctx)
        assert stopped.output.reply_mode == "no_reply"
    finally:
        await first.shutdown()
    second = build_runtime(settings)
    await second.initialize()
    try:
        agent = second.agents.get("whatsapp")
        result = await agent.run(whatsapp("Fictional question"), ctx)
        assert result.output.reply_mode == "no_reply" and result.status == "escalated"
        foreign = await agent.run(whatsapp("Fictional question"), other_organization(ctx))
        assert foreign.output.reply_mode == "free_text"
        context = ToolCallContext(
            manager, manager.tenant_id, "fixture", "whatsapp", frozenset({"whatsapp.send_message"})
        )
        queued = await second.gateway.invoke(
            context,
            "whatsapp.send_message",
            {
                "conversation_id": "fictional-shared-id",
                "to_e164": "+971500000001",
                "text": "Fictional reply",
                "consent_whatsapp": True,
                "last_inbound_at": datetime.now(UTC).isoformat(),
            },
        )
        await second.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
        with pytest.raises(PolicyViolationError):
            await second.gateway.execute_approved(queued.approval_id, manager)
        assert second.integrations.whatsapp.outbox == []
    finally:
        await second.shutdown()


async def test_unconfigured_runtime_keeps_existing_memory_backend(settings):
    settings.agent_memory_path = None
    runtime = build_runtime(settings)
    try:
        assert isinstance(runtime.deps.memory, InMemoryConversationMemory)
    finally:
        await runtime.shutdown()


async def test_unusable_configured_storage_fails_initialization(settings, tmp_path):
    settings.agent_memory_path = str(tmp_path)
    runtime = build_runtime(settings)
    try:
        with pytest.raises((sqlite3.DatabaseError, OSError)):
            await runtime.initialize()
        assert isinstance(runtime.deps.memory, SqliteConversationMemory)
    finally:
        await runtime.shutdown()


@pytest.mark.skipif(os.name == "nt", reason="Unix file mode check")
async def test_new_database_has_private_file_permissions(tmp_path):
    memory = SqliteConversationMemory(str(tmp_path / "private" / "memory.sqlite3"))
    await memory.initialize()
    assert memory.path.stat().st_mode & 0o777 == 0o600
    assert memory.path.parent.stat().st_mode & 0o777 == 0o700
