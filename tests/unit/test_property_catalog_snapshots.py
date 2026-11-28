"""Read-only property catalogs must not share mutable prices or payment plans."""

from decimal import Decimal

import pytest

from database.seeds.demo_catalog import DEMO_LISTINGS
from schemas.properties.models import Availability
from tools.property.catalog import InMemoryPropertyCatalog
from tools.property.tools import PropertyMatchTool, PropertySearchTool


def fictional_listing():
    listing = next(item for item in DEMO_LISTINGS if item.payment_plan is not None).model_copy(
        deep=True
    )
    assert listing.payment_plan is not None
    return listing


def change_listing(listing):
    listing.price_aed = Decimal(1)
    listing.availability = Availability.SOLD
    listing.is_demo = False
    listing.source = "Changed outside catalog"
    listing.payment_plan.name = "Changed outside catalog"


@pytest.mark.parametrize("boundary", ["list-input", "generator-input", "get", "all"])
async def test_catalog_owns_and_returns_independent_nested_records(boundary):
    original = fictional_listing()
    expected = original.model_copy(deep=True)
    catalog = InMemoryPropertyCatalog(
        iter([original]) if boundary == "generator-input" else [original]
    )
    if boundary in {"list-input", "generator-input"}:
        target = original
    elif boundary == "get":
        target = await catalog.get(original.listing_id)
    else:
        target = (await catalog.all_listings())[0]
    change_listing(target)
    assert await catalog.get(expected.listing_id) == expected
    assert await catalog.all_listings() == [expected]


async def test_two_catalogs_do_not_share_records_or_constructor_inputs():
    shared = fictional_listing()
    expected = shared.model_copy(deep=True)
    first, second = InMemoryPropertyCatalog([shared]), InMemoryPropertyCatalog([shared])
    change_listing(await first.get(shared.listing_id))
    assert await first.get(expected.listing_id) == expected
    assert await second.get(expected.listing_id) == expected
    assert shared == expected


async def test_default_catalogs_cannot_change_global_demo_seed():
    seed = next(item for item in DEMO_LISTINGS if item.payment_plan is not None)
    expected = seed.model_copy(deep=True)
    first, second = InMemoryPropertyCatalog(), InMemoryPropertyCatalog()
    try:
        change_listing(await first.get(seed.listing_id))
        assert seed == expected
        assert await second.get(seed.listing_id) == expected
        assert await InMemoryPropertyCatalog().get(seed.listing_id) == expected
    finally:
        # The pre-fix implementation aliases the seed; leave other tests independent.
        seed.price_aed = expected.price_aed
        seed.availability = expected.availability
        seed.is_demo = expected.is_demo
        seed.source = expected.source
        seed.payment_plan.name = expected.payment_plan.name


@pytest.mark.parametrize(
    "tool_class,key", [(PropertySearchTool, "listings"), (PropertyMatchTool, "recommendations")]
)
async def test_tool_response_edits_do_not_change_catalog_facts(tool_class, key):
    source = fictional_listing()
    expected = source.model_copy(deep=True)
    catalog = InMemoryPropertyCatalog([source])
    result = await tool_class(catalog).execute({"limit": 1})
    assert len(result[key]) == 1
    listing = result[key][0] if key == "listings" else result[key][0]["listing"]
    listing["price_aed"] = "1"
    listing["is_demo"] = False
    listing["payment_plan"]["name"] = "Changed response"
    assert await catalog.get(source.listing_id) == expected


async def test_unknown_listing_and_empty_catalog_remain_empty():
    catalog = InMemoryPropertyCatalog(())
    assert await catalog.get("fictional-missing-id") is None
    assert await catalog.all_listings() == []


async def test_supplied_source_workspace_does_not_restore_demo_inventory(settings, tmp_path, ctx):
    from workflows.runtime import build_runtime

    settings.agent_knowledge_path = str(tmp_path / "sources.sqlite3")
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        runtime.assigned_sources.add(
            ctx.tenant_id,
            "property_recommendation",
            "Fictional supplied property facts",
            "text",
            ["Fictional gardens have a viewing room."],
            customer_safe=True,
        )
        for name, key in [("property.search", "listings"), ("property.match", "recommendations")]:
            result = await runtime.agents.get("property_recommendation").use_tool(
                ctx, name, {"limit": 5}
            )
            assert result.data[key] == []
        result = await runtime.agents.get("property_recommendation").run(
            {"criteria": {"limit": 5}}, ctx
        )
        assert result.output.recommendations == []
        assert result.output.contains_demo_data is False
    finally:
        await runtime.shutdown()
