import json
from types import SimpleNamespace

import pytest

from pathlib import Path

from app.vinted import VintedClient, extract_item_detail, extract_jsonld_items


class FakeResponse:
    def __init__(self, status_code: int, text: str, payload=None, url: str | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.url = url

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


def test_extract_live_shape_item_detail_fixture() -> None:
    document = (Path(__file__).parent / "fixtures/vinted/item_detail.html").read_text()
    detail = extract_item_detail(document, "987654", "https://www.vinted.fr/items/987654")
    assert detail.description == "Set complet, notice incluse."
    assert detail.photos == [
        "https://images.example/42035-1.webp",
        "https://images.example/42035-2.webp",
    ]
    assert detail.condition == "Très bon état"
    assert detail.size == "Taille unique"
    assert detail.category_id == "1767"
    assert detail.category_path == ["Enfants", "Jeux de construction"]
    assert detail.colors == ["Bleu", "Blanc"]
    assert detail.favourite_count == 12
    assert detail.view_count == 84
    assert detail.seller["rating"] == 4.9
    assert detail.seller["reviews_count"] == 127


def test_extract_current_next_flight_item_detail() -> None:
    plugins = [
        {"data": {"photos": [{"url": "https://images1.vinted.net/item.webp"}]}, "name": "gallery"},
        {"data": {"description": "Console complète"}, "name": "description"},
        {"data": {"breadcrumbs": [{"title": "Électronique"}, {"title": "Consoles"}], "catalog_id": "3013"}, "name": "breadcrumbs"},
        {"data": {"attributes": [
            {"code": "status", "data": {"value": "Comme neuf"}},
            {"code": "size", "data": {"value": "Taille unique"}},
            {"code": "color", "data": {"value": "Noir, Blanc"}},
        ]}, "name": "attributes"},
        {"data": {"favourite_count": 9}, "name": "favourite"},
        {"data": {"name": "vendeur", "feedback_reputation": .98, "feedback_count": 42}, "name": "seller"},
    ]
    product = {"@type": "Product", "name": "Nintendo Switch 2", "description": "Console complète"}
    flight = "\n".join(json.dumps(value, ensure_ascii=False) for value in plugins)
    flight += "\n" + json.dumps({"jsonLd": product}, ensure_ascii=False)
    document = f"<script>self.__next_f.push({json.dumps([1, flight], ensure_ascii=False)})</script>"
    detail = extract_item_detail(document, "123", "https://www.vinted.fr/items/123")
    assert detail.title == "Nintendo Switch 2"
    assert detail.description == "Console complète"
    assert detail.photos == ["https://images1.vinted.net/item.webp"]
    assert detail.condition == "Comme neuf"
    assert detail.category_id == "3013"
    assert detail.category_path == ["Électronique", "Consoles"]
    assert detail.colors == ["Noir", "Blanc"]
    assert detail.favourite_count == 9
    assert detail.seller["rating"] == 4.9


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


@pytest.mark.asyncio
async def test_detail_probes_api_then_parses_html_fallback(monkeypatch) -> None:
    document = (Path(__file__).parent / "fixtures/vinted/item_detail.html").read_text()
    http = FakeHTTP([
        FakeResponse(200, "<html></html>"),
        FakeResponse(404, '{"code":"NOT_FOUND"}'),
        FakeResponse(404, '{"code":"NOT_FOUND"}'),
        FakeResponse(200, document, url="https://www.vinted.fr/items/987654-lego"),
    ])
    client = VintedClient(http=http)

    async def no_throttle():
        return None

    monkeypatch.setattr(client, "_throttle", no_throttle)
    detail = await client.detail("987654")
    assert detail.description == "Set complet, notice incluse."
    assert [value.status_code for value in client.request_history] == [404, 404, 200]
    assert client.request_history[-1].final_url == "https://www.vinted.fr/items/987654-lego"
    assert client.request_history[-1].fallback_used


@pytest.mark.asyncio
async def test_detail_404_is_deleted_not_parse_error(monkeypatch) -> None:
    http = FakeHTTP([
        FakeResponse(200, "<html></html>"),
        FakeResponse(404, "route missing"),
        FakeResponse(404, "route missing"),
        FakeResponse(404, "article supprimé", url="https://www.vinted.fr/items/404"),
    ])
    client = VintedClient(http=http)

    async def no_throttle():
        return None

    monkeypatch.setattr(client, "_throttle", no_throttle)
    detail = await client.detail("404")
    assert detail.status == "DELETED"
    assert client.request_history[-1].response_body == "article supprimé"


@pytest.mark.asyncio
async def test_detail_parse_error_keeps_http_final_url_and_body(monkeypatch) -> None:
    body = "<html><title>Unexpected shell</title>" + "x" * 1000
    http = FakeHTTP([
        FakeResponse(200, "<html></html>"),
        FakeResponse(404, "route missing"),
        FakeResponse(404, "route missing"),
        FakeResponse(200, body, url="https://www.vinted.fr/items/12-shell"),
    ])
    client = VintedClient(http=http)

    async def no_throttle():
        return None

    monkeypatch.setattr(client, "_throttle", no_throttle)
    with pytest.raises(Exception, match="http=200"):
        await client.detail("12")
    diagnostics = client.request_history[-1]
    assert diagnostics.final_url == "https://www.vinted.fr/items/12-shell"
    assert diagnostics.response_body == body[:500]


@pytest.mark.asyncio
async def test_detail_retry_failure_keeps_last_http_url_and_body(monkeypatch) -> None:
    body = "blocked by edge" + "x" * 700
    http = FakeHTTP([
        FakeResponse(200, "<html></html>"),
        FakeResponse(404, "route missing"),
        FakeResponse(404, "route missing"),
        *[
            FakeResponse(403, body, url="https://www.vinted.fr/items/12-blocked")
            for _ in range(4)
        ],
    ])
    client = VintedClient(http=http)

    async def no_wait(*args):
        return None

    monkeypatch.setattr(client, "_throttle", no_wait)
    monkeypatch.setattr("app.vinted.asyncio.sleep", no_wait)
    with pytest.raises(Exception) as caught:
        await client.detail("12")
    message = str(caught.value)
    assert "http=403" in message
    assert "url=https://www.vinted.fr/items/12-blocked" in message
    assert body[:500] in message
