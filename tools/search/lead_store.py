"""Lead store used for duplicate detection.

The in-memory store powers local demos/tests. Production should implement the
same protocol on ``database/repositories/leads.py``.
"""

from __future__ import annotations

from typing import Protocol

from schemas.leads.models import NormalizedLead


class LeadStore(Protocol):
    async def find_by_dedupe_keys(self, tenant_id: str, keys: list[str]) -> list[NormalizedLead]: ...

    async def save(self, lead: NormalizedLead) -> None: ...

    async def list(self, tenant_id: str) -> list[NormalizedLead]: ...


class InMemoryLeadStore:
    def __init__(self) -> None:
        self._leads: dict[str, NormalizedLead] = {}

    async def find_by_dedupe_keys(self, tenant_id: str, keys: list[str]) -> list[NormalizedLead]:
        wanted = set(keys)
        return [
            lead
            for lead in self._leads.values()
            if lead.tenant_id == tenant_id and wanted.intersection(lead.dedupe_keys)
        ]

    async def save(self, lead: NormalizedLead) -> None:
        self._leads[lead.lead_id] = lead

    async def list(self, tenant_id: str) -> list[NormalizedLead]:
        return [lead for lead in self._leads.values() if lead.tenant_id == tenant_id]
