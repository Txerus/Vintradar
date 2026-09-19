import json
from types import SimpleNamespace

import pytest

from app.vinted import VintedClient, extract_jsonld_items


class FakeResponse:
    def __init__(self, status_code: int, text: str, payload=None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


class FakeHTTP:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.cookies = {"access_token_web": "secret", "anon_id": "anonymous-id"}
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_extract_jsonld_item_list() -> None:
    document = """
    <html><script type="application/ld+json">
    {"@type":"ItemList","itemListElement":[{"position":1,"item":{
      "@type":"Product","name":"Console rétro","url":"https://www.vinted.fr/items/987-console",
      "image":"https://images.example/987.jpg","offers":{"price":"79.90","priceCurrency":"EUR"}
    }}]}
    </script></html>
    """
    items = extract_jsonld_items(document)
    assert items == [
        {
            "id": "987",
            "title": "Console rétro",
            "description": "",
            "price": {"amount": "79.90", "currency_code": "EUR"},
            "url": "https://www.vinted.fr/items/987-console",
            "photo": {"url": "https://images.example/987.jpg"},
            "photos": [{"url": "https://images.example/987.jpg"}],
            "status": None,
            "_source": "json-ld",
        }
    ]


@pytest.mark.asyncio
async def test_new_catalogue_endpoint_headers_and_attribute_filters() -> None:
    http = FakeHTTP(
        [
            FakeResponse(200, '<meta name="csrf-token" content="csrf-secret">'),
            FakeResponse(200, '{"items": []}', {"items": []}),
        ]
    )
    client = VintedClient(http=http)
    alert = SimpleNamespace(
        include_terms=["lego"],
        min_price=10,
        max_price=100,
        filters={"catalog": "123,456", "status": ["1", "2"]},
    )
    assert await client.search(alert) == []
    url, call = http.calls[1]
    assert url == "https://api.vinted.fr/svc-catalogue/items"
    assert call["headers"]["X-Anon-Id"] == "anonymous-id"
    assert call["headers"]["X-Csrf-Token"] == "csrf-secret"
    assert ("attribute_ids[catalog]", "123") in call["params"]
    assert ("attribute_ids[status]", "2") in call["params"]
    assert client.request_history[0].headers == ("Accept", "Referer", "X-Anon-Id", "X-Csrf-Token")


@pytest.mark.asyncio
async def test_api_error_falls_back_to_catalog_jsonld() -> None:
    document = """
    <script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"item":{"name":"Article","url":"https://www.vinted.fr/items/321-a","offers":{"price":12,"priceCurrency":"EUR"}}}
    ]}</script>
    """
    http = FakeHTTP(
        [
            FakeResponse(200, "<html></html>"),
            FakeResponse(404, "route not found"),
            FakeResponse(200, document),
        ]
    )
    client = VintedClient(http=http)
    alert = SimpleNamespace(include_terms=["article"], min_price=None, max_price=None, filters={})
    items = await client.search(alert)
    assert items[0]["id"] == "321"
    assert len(client.request_history) == 2
    assert client.request_history[0].response_body == "route not found"
    assert client.request_history[1].fallback_used
