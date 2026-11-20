from __future__ import annotations

from typing import Any, ClassVar

from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from schemas.properties.models import PropertySearchCriteria
from tools.base import BaseTool, ToolSpec
from tools.property.catalog import PropertyCatalog
from tools.property.matching import is_eligible, match_properties


class PropertySearchTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="property.search",
        description="Filter the property catalog by hard criteria",
        category=ActionCategory.READ,
        permission=Permission.PROPERTIES_READ,
    )

    def __init__(self, catalog: PropertyCatalog) -> None:
        self._catalog = catalog

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        criteria = PropertySearchCriteria.model_validate(payload)
        listings = [lst for lst in await self._catalog.all_listings() if is_eligible(lst, criteria)]
        return {"listings": [lst.model_dump(mode="json") for lst in listings[: criteria.limit]]}


class PropertyMatchTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="property.match",
        description="Rank eligible properties against customer requirements",
        category=ActionCategory.READ,
        permission=Permission.PROPERTIES_READ,
    )

    def __init__(self, catalog: PropertyCatalog) -> None:
        self._catalog = catalog

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        criteria = PropertySearchCriteria.model_validate(payload)
        ranked = match_properties(await self._catalog.all_listings(), criteria)
        return {"recommendations": [r.model_dump(mode="json") for r in ranked]}
