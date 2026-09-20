import json

import httpx
import pytest

from app.config import settings
from app.price_sources import BrickLinkSource, BricksetSource, PriceChartingSource, RebrickableValidator


class FixedRates:
    async def usd_to_eur(self):
        return 0.8


@pytest.mark.asyncio
async def test_rebrickable_validation_and_pricecharting_conversion(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "rebrickable" in request.url.host:
            return httpx.Response(200, json={"set_num": "42035-1", "name": "Mining Truck"}, request=request)
        if request.url.path == "/api/products":
            return httpx.Response(200, json={"products": [{"id": "123"}]}, request=request)
        return httpx.Response(
            200,
            json={"product-name": "PAL Pokemon", "cib-price": 5000, "loose-price": 3000, "new-price": 7000},
            request=request,
        )

    monkeypatch.setattr(settings, "pricecharting_token", "private-test-token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        validation = await RebrickableValidator("rebrickable-test", client).validate("42035")
        source = PriceChartingSource(client, FixedRates())
        quote = await source.quote("game:switch2:pokemon-legendes-za:standard", "VERY_GOOD")
    assert validation["name"] == "Mining Truck"
    assert quote.value == 40
    assert quote.meta["field"] == "cib-price"
    assert quote.meta["indicative"] is True


@pytest.mark.asyncio
async def test_bricklink_and_brickset_keep_sources_separate(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bricklink" in request.url.host:
            assert request.url.params["guide_type"] == "sold"
            assert request.url.params["region"] == "europe"
            assert request.url.params["currency_code"] == "EUR"
            assert request.headers["Authorization"].startswith("OAuth ")
            return httpx.Response(200, json={"data": {"avg_price": "41.50", "unit_quantity": 12}}, request=request)
        return httpx.Response(
            200,
            json={"sets": [{"name": "Mining Truck", "LEGOCom": {"retailPrice": 49.99}}]},
            request=request,
        )

    for name in (
        "bricklink_consumer_key", "bricklink_consumer_secret",
        "bricklink_token_value", "bricklink_token_secret",
    ):
        monkeypatch.setattr(settings, name, f"{name}-test")
    monkeypatch.setattr(settings, "brickset_api_key", "brickset-test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sold = await BrickLinkSource(client).quote("lego:42035", "VERY_GOOD")
        retail = await BricksetSource(client).quote("lego:42035", "VERY_GOOD")
    assert sold.source == "bricklink_sold_europe"
    assert sold.value == 41.5
    assert retail.source == "brickset_retail"
    assert retail.value == 49.99
