import asyncio
import hashlib
import html
import json
import random
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urlparse

from curl_cffi.requests import AsyncSession

from app.config import settings


class VintedError(RuntimeError):
    pass


@dataclass(frozen=True)
class RequestDiagnostics:
    url: str
    headers: tuple[str, ...]
    status_code: int | None = None
    response_body: str | None = None
    fallback_used: bool = False
    final_url: str | None = None


@dataclass(frozen=True)
class ItemDetail:
    external_id: str
    title: str
    description: str
    photos: list[str]
    brand: str | None
    size: str | None
    condition: str | None
    category_id: str | None
    category_name: str | None
    category_path: list[str]
    colors: list[str]
    published_at: str | None
    favourite_count: int | None
    view_count: int | None
    shipping: float | None
    status: str
    seller: dict[str, Any]
    source_url: str


class _JSONLDScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._chunks: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value for key, value in attrs}
        if tag.lower() == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self._capturing = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self.scripts.append("".join(self._chunks))
            self._capturing = False
            self._chunks = []


def extract_jsonld_items(document: str) -> list[dict[str, Any]]:
    parser = _JSONLDScriptParser()
    parser.feed(document)
    results: list[dict[str, Any]] = []
    for raw in parser.scripts:
        try:
            payload = json.loads(html.unescape(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") != "ItemList":
                continue
            for position, element in enumerate(node.get("itemListElement") or [], start=1):
                item = element.get("item", element) if isinstance(element, dict) else None
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "")
                external_id = _item_id(item, url, position)
                offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
                image = item.get("image")
                raw_images = image if isinstance(image, list) else [image]
                images = []
                for candidate in raw_images:
                    if isinstance(candidate, dict):
                        candidate = candidate.get("url") or candidate.get("contentUrl")
                    if candidate:
                        images.append(str(candidate))
                image = images[0] if images else None
                results.append(
                    {
                        "id": external_id,
                        "title": item.get("name") or item.get("headline") or "Annonce Vinted",
                        "description": item.get("description") or "",
                        "price": {
                            "amount": str(offers.get("price") or item.get("price") or 0),
                            "currency_code": offers.get("priceCurrency") or "EUR",
                        },
                        "url": url,
                        "photo": {"url": image} if image else {},
                        "photos": [{"url": value} for value in images],
                        "status": item.get("itemCondition"),
                        "_source": "json-ld",
                    }
                )
    return results


def _jsonld_products(document: str) -> list[dict[str, Any]]:
    parser = _JSONLDScriptParser()
    parser.feed(document)
    products: list[dict[str, Any]] = []
    for raw in parser.scripts:
        try:
            payload = json.loads(html.unescape(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        for node in payload if isinstance(payload, list) else [payload]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                products.append(node)
    return products


def _flight_payload(document: str) -> str:
    chunks: list[str] = []
    for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)\s*</script>", document, re.DOTALL):
        try:
            value = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
            chunks.append(value[1])
    return "\n".join(chunks)


def _flight_plugins(document: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return item-page plugin payloads and the embedded Product JSON-LD.

    The current Next/RSC page embeds independently valid JSON objects inside
    flight strings. Decoding those objects is more robust than matching fields
    across the entire minified document.
    """
    flight = _flight_payload(document)
    decoder = json.JSONDecoder()
    plugins: dict[str, Any] = {}
    product: dict[str, Any] = {}
    starts = {match.start() for match in re.finditer(r'\{"data":', flight)}
    for marker in re.finditer(r'"jsonLd"\s*:\s*', flight):
        starts.add(marker.end())
    for start in sorted(starts):
        try:
            value, _ = decoder.raw_decode(flight, start)
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                if current.get("@type") == "Product":
                    product = current
                name = current.get("name")
                if isinstance(name, str) and isinstance(current.get("data"), dict):
                    plugins[name] = current["data"]
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
    return plugins, product


def _value_title(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("title") or value.get("name") or value.get("value")
    return str(value) if value not in (None, "") else None


def _photo_values(raw: Any) -> list[str]:
    values: list[str] = []
    for photo in raw if isinstance(raw, list) else [raw]:
        if isinstance(photo, dict):
            candidate = photo.get("full_size_url") or photo.get("url") or photo.get("contentUrl")
        else:
            candidate = photo
        if candidate and str(candidate) not in values:
            values.append(str(candidate))
    return values


def _first_match(text: str, patterns: tuple[str, ...], cast: type = str) -> Any:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return cast(match.group(1))
            except (TypeError, ValueError):
                return None
    return None


def extract_item_detail(document: str, external_id: str, source_url: str) -> ItemDetail:
    products = _jsonld_products(document)
    plugins, flight_product = _flight_plugins(document)
    product = products[0] if products else flight_product
    flight = _flight_payload(document)
    combined = html.unescape(flight)
    offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
    gallery = plugins.get("gallery") or {}
    photos = _photo_values(gallery.get("photos") or product.get("image") or [])
    brand_value = product.get("brand")
    brand = brand_value.get("name") if isinstance(brand_value, dict) else brand_value
    seller_plugin = plugins.get("seller") or {}
    reputation = seller_plugin.get("feedback_reputation")
    if reputation is None:
        reputation = _first_match(combined, (r'"feedback_reputation"\s*:\s*([0-9.]+)',), float)
    if reputation is not None and reputation <= 1:
        reputation *= 5
    seller = {
        "id": seller_plugin.get("id") or _first_match(combined, (r'"seller_id"\s*:\s*"?([0-9]+)', r'"user_id"\s*:\s*"?([0-9]+)')),
        "name": seller_plugin.get("name") or seller_plugin.get("username") or _first_match(combined, (r'"username"\s*:\s*"([^"]+)"',)),
        "rating": reputation,
        "reviews_count": seller_plugin.get("feedback_count") or _first_match(combined, (r'"feedback_count"\s*:\s*([0-9]+)',), int),
        "location": _first_match(combined, (r'"(?:city|country_title|country)"\s*:\s*"([^"]+)"',)),
        "created_at": _first_match(combined, (r'"(?:account_created_at|created_at)"\s*:\s*"([^"]+)"',)),
        "last_login_at": _first_match(combined, (r'"last_logged_on_ts"\s*:\s*"([^"]+)"',)),
    }
    attributes = (plugins.get("attributes") or {}).get("attributes") or []
    legacy_attribute_block = _first_match(
        combined,
        (rf'"attributes"\s*:\s*(\[.*?\])\s*,\s*"item_id"\s*:\s*"{re.escape(external_id)}"',),
    ) or ""
    def attribute(code: str) -> str | None:
        for item in attributes:
            if isinstance(item, dict) and item.get("code") == code:
                data = item.get("data")
                if isinstance(data, dict):
                    return _value_title(data.get("value")) or _value_title(data.get("title"))
                return _value_title(data)
        attribute_block = json.dumps(attributes, ensure_ascii=False) if attributes else legacy_attribute_block
        return _first_match(
            attribute_block,
            (rf'"code"\s*:\s*"{code}".*?"value"\s*:\s*"([^"]+)"',),
        )
    availability = str(offers.get("availability") or "").lower()
    if re.search(r'"is_reserved"\s*:\s*true', combined):
        status = "RESERVED"
    elif re.search(r'"is_sold"\s*:\s*true', combined) or "outofstock" in availability or "soldout" in availability:
        status = "SOLD_CONFIRMED"
    else:
        status = "ACTIVE"
    breadcrumb_plugin = plugins.get("breadcrumbs") or {}
    breadcrumb_values = breadcrumb_plugin.get("breadcrumbs") or []
    category_path = [str(value.get("title")) for value in breadcrumb_values if isinstance(value, dict) and value.get("title")]
    legacy_breadcrumbs = _first_match(
        combined,
        (rf'"breadcrumbs"\s*:\s*(\[.*?\])\s*,\s*"catalog_id"\s*:\s*"?(\d+)"?\s*,\s*"item_id"\s*:\s*"{re.escape(external_id)}"',),
    ) or ""
    if not category_path:
        category_path = re.findall(r'"title"\s*:\s*"([^"]+)"', legacy_breadcrumbs)
    description = (plugins.get("description") or {}).get("description") or product.get("description") or ""
    summary = plugins.get("summary") or {}
    title = product.get("name") or summary.get("title") or _first_match(combined, (r'"title"\s*:\s*"([^"]+)"',))
    return ItemDetail(
        external_id=external_id,
        title=str(title or "Annonce Vinted"),
        description=str(description),
        photos=photos,
        brand=str(brand) if brand else _first_match(combined, (r'"brand_title"\s*:\s*"([^"]+)"',)),
        size=attribute("size"),
        condition=attribute("status"),
        category_id=(
            str(breadcrumb_plugin.get("catalog_id")) if breadcrumb_plugin.get("catalog_id")
            else _first_match(
                combined,
                (rf'"breadcrumbs"\s*:\s*\[.*?\]\s*,\s*"catalog_id"\s*:\s*"?(\d+)"?\s*,\s*"item_id"\s*:\s*"{re.escape(external_id)}"',),
            )
        ),
        category_name=category_path[-1] if category_path else None,
        category_path=category_path,
        colors=[value.strip() for value in (attribute("color") or "").split(",") if value.strip()],
        published_at=None,
        favourite_count=(plugins.get("favourite") or {}).get("favourite_count") or _first_match(combined, (r'"favourite_count"\s*:\s*([0-9]+)',), int),
        view_count=_first_match(combined, (r'"view_count"\s*:\s*([0-9]+)',), int),
        shipping=_first_match(combined, (r'"shipping[^"]*"\s*:\s*\{[^{}]*"amount"\s*:\s*"([0-9.]+)"',), float),
        status=str(status).upper(),
        seller=seller,
        source_url=source_url,
    )


def _item_id(item: dict[str, Any], url: str, position: int) -> str:
    identifier = item.get("productID") or item.get("sku") or item.get("@id")
    if identifier:
        return str(identifier).rstrip("/").rsplit("/", 1)[-1]
    match = re.search(r"/(?:items?|articles?)/(\d+)", url)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return match.group(1) if match else f"jsonld-{position}-{digest}"


def _csrf_token(document: str, cookies: Any) -> str | None:
    for name in ("csrf_token", "_csrf", "XSRF-TOKEN"):
        value = cookies.get(name)
        if value:
            return str(value)
    patterns = (
        r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token["\']',
        r'["\']csrfToken["\']\s*:\s*["\']([^"\']+)',
    )
    for pattern in patterns:
        match = re.search(pattern, document, re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
    return None


class VintedClient:
    DETAIL_API_TEMPLATES = (
        "/svc-item-details/items/{id}",
        "/api/v2/items/{id}/details",
    )

    def __init__(self, http: AsyncSession | None = None) -> None:
        self.base = settings.vinted_domain.rstrip("/")
        parsed = urlparse(self.base)
        host = parsed.netloc.removeprefix("www.")
        self.api_base = f"{parsed.scheme or 'https'}://api.{host}"
        self.http = http or AsyncSession(impersonate="chrome")
        self.ready = False
        self.csrf_token: str | None = None
        self.last_diagnostics: RequestDiagnostics | None = None
        self.request_history: list[RequestDiagnostics] = []
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._detail_api_probed = False
        self._detail_api_template: str | None = None

    def _record(self, diagnostics: RequestDiagnostics) -> None:
        self.last_diagnostics = diagnostics
        self.request_history.append(diagnostics)

    async def _throttle(self) -> None:
        async with self._rate_lock:
            interval = 60 / max(1, settings.scan_global_rpm)
            delay = interval - (time.monotonic() - self._last_request_at)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()

    async def bootstrap(self) -> None:
        response = await self.http.get(self.base + "/", timeout=20)
        if response.status_code >= 400:
            raise VintedError(f"bootstrap {response.status_code}: {response.text[:1000]}")
        self.csrf_token = _csrf_token(response.text, self.http.cookies)
        self.ready = True

    def search_params(self, alert: Any) -> list[tuple[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("search_text", " ".join(alert.include_terms)),
            ("order", "newest_first"),
            ("per_page", 48),
            ("page", 1),
        ]
        if alert.min_price is not None:
            params.append(("price_from", alert.min_price))
        if alert.max_price is not None:
            params.append(("price_to", alert.max_price))
        for name, raw_value in (getattr(alert, "filters", None) or {}).items():
            values = raw_value if isinstance(raw_value, list) else str(raw_value).split(",")
            for value in values:
                clean = str(value).strip()
                if clean:
                    params.append((f"attribute_ids[{name}]", clean))
        return params

    def request_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Referer": self.base + "/catalog"}
        anon_id = self.http.cookies.get("anon_id")
        if anon_id:
            headers["X-Anon-Id"] = str(anon_id)
        if self.csrf_token:
            headers["X-Csrf-Token"] = self.csrf_token
        return headers

    async def search(self, alert: Any, *, page: int = 1, search_text: str | None = None) -> list[dict[str, Any]]:
        self.request_history = []
        if not self.ready:
            await self.bootstrap()
        params = self.search_params(alert)
        params = [(key, page if key == "page" else value) for key, value in params]
        if search_text is not None:
            params = [(key, search_text if key == "search_text" else value) for key, value in params]
        api_url = self.api_base + "/svc-catalogue/items"
        last_error: str | None = None
        for attempt in range(4):
            await self._throttle()
            headers = self.request_headers()
            response = await self.http.get(api_url, params=params, headers=headers, timeout=20)
            full_url = f"{api_url}?{urlencode(params)}"
            body = response.text[:4000] if response.status_code >= 400 else None
            self._record(RequestDiagnostics(
                url=full_url,
                headers=tuple(sorted(headers)),
                status_code=response.status_code,
                response_body=body,
            ))
            if response.status_code == 401:
                self.ready = False
                await self.bootstrap()
                last_error = "401"
                continue
            if response.status_code in (403, 429):
                last_error = f"{response.status_code}: {body}"
                await asyncio.sleep((2**attempt) + random.random() * 2)
                continue
            if response.status_code < 400:
                try:
                    payload = response.json()
                except (ValueError, TypeError) as error:
                    last_error = f"invalid JSON: {error}; body={response.text[:1000]}"
                    break
                items = payload.get("items", []) if isinstance(payload, dict) else []
                if isinstance(items, list):
                    return items
                last_error = f"invalid items payload: {response.text[:1000]}"
                break
            last_error = f"{response.status_code}: {body}"
            break

        fallback = await self._search_jsonld(params)
        if fallback:
            return fallback
        detail = last_error or "empty JSON-LD fallback"
        raise VintedError(f"Vinted search failed ({detail})")

    async def detail(self, external_id: str) -> ItemDetail:
        if not self.ready:
            await self.bootstrap()
        api_detail = await self._detail_api(external_id)
        if api_detail is not None:
            return api_detail
        url = f"{self.base}/items/{external_id}"
        last_status: int | None = None
        last_url = url
        last_body = ""
        for attempt in range(4):
            await self._throttle()
            response = await self.http.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Referer": self.base + "/",
                    "X-Next-App": "marketplace-web",
                },
                timeout=25,
            )
            final_url = str(getattr(response, "url", None) or url)
            body = response.text[:500] if response.status_code >= 400 else None
            last_status, last_url, last_body = response.status_code, final_url, body or ""
            self._record(RequestDiagnostics(
                url=url,
                headers=("Accept", "Referer", "X-Next-App"),
                status_code=response.status_code,
                response_body=body,
                fallback_used=True,
                final_url=final_url,
            ))
            if response.status_code in (404, 410):
                return ItemDetail(
                    external_id, "", "", [], None, None, None, None, None, [], [], None,
                    None, None, None, "DELETED", {}, final_url,
                )
            if response.status_code in (403, 429):
                await asyncio.sleep((2**attempt) + random.random())
                continue
            if response.status_code >= 400:
                raise VintedError(
                    f"item detail HTTP {response.status_code}; url={final_url}; body={body}"
                )
            detail = extract_item_detail(response.text, external_id, final_url)
            if not detail.title or (not detail.description and not detail.photos):
                snippet = response.text[:500]
                self._record(RequestDiagnostics(
                    url=url,
                    headers=("Accept", "Referer", "X-Next-App"),
                    status_code=response.status_code,
                    response_body=snippet,
                    fallback_used=True,
                    final_url=final_url,
                ))
                raise VintedError(
                    "item page contained no usable Product JSON-LD or hydration data; "
                    f"http={response.status_code}; url={final_url}; body={snippet}"
                )
            return detail
        raise VintedError(
            f"item detail failed; http={last_status}; url={last_url}; body={last_body}"
        )

    async def _detail_api(self, external_id: str) -> ItemDetail | None:
        templates = [self._detail_api_template] if self._detail_api_template else (
            [] if self._detail_api_probed else list(self.DETAIL_API_TEMPLATES)
        )
        for template in templates:
            if template is None:
                continue
            url = self.api_base + template.format(id=external_id)
            await self._throttle()
            headers = {
                **self.request_headers(),
                "X-Next-App": "marketplace-web",
                "Platform": "web",
                "Locale": "fr-FR",
            }
            response = await self.http.get(url, headers=headers, timeout=20)
            final_url = str(getattr(response, "url", None) or url)
            snippet = response.text[:500]
            self._record(RequestDiagnostics(
                url=url,
                headers=tuple(sorted(headers)),
                status_code=response.status_code,
                response_body=snippet if response.status_code >= 400 else None,
                final_url=final_url,
            ))
            if response.status_code >= 400:
                continue
            try:
                payload = response.json()
                detail = self._detail_from_api(payload, external_id, final_url)
            except (ValueError, TypeError, KeyError):
                continue
            self._detail_api_template = template
            self._detail_api_probed = True
            return detail
        if not self._detail_api_template:
            self._detail_api_probed = True
        return None

    @staticmethod
    def _detail_from_api(payload: dict[str, Any], external_id: str, source_url: str) -> ItemDetail:
        raw = payload.get("item") or payload.get("data") or payload
        if isinstance(raw, dict) and isinstance(raw.get("item"), dict):
            raw = raw["item"]
        if not isinstance(raw, dict) or not (raw.get("title") or raw.get("description")):
            raise ValueError("API detail payload contained no item")
        photos = _photo_values(raw.get("photos") or raw.get("photo"))
        brand = _value_title(raw.get("brand")) or _value_title(raw.get("brand_title"))
        size = _value_title(raw.get("size")) or _value_title(raw.get("size_title"))
        condition = _value_title(raw.get("status")) or _value_title(raw.get("condition"))
        catalog = raw.get("catalog") if isinstance(raw.get("catalog"), dict) else {}
        breadcrumbs = raw.get("breadcrumbs") or catalog.get("breadcrumbs") or []
        category_path = [
            str(value.get("title")) for value in breadcrumbs
            if isinstance(value, dict) and value.get("title")
        ]
        colors_raw = raw.get("colors") or raw.get("color_titles") or []
        colors = [value for value in (_value_title(item) for item in colors_raw) if value]
        seller = raw.get("user") or raw.get("seller") or {}
        availability = str(raw.get("status") or raw.get("availability") or "").lower()
        status = (
            "SOLD_CONFIRMED" if raw.get("is_sold") or "sold" in availability
            else "RESERVED" if raw.get("is_reserved") or "reserved" in availability
            else "ACTIVE"
        )
        return ItemDetail(
            external_id=external_id,
            title=str(raw.get("title") or "Annonce Vinted"),
            description=str(raw.get("description") or ""),
            photos=photos,
            brand=brand,
            size=size,
            condition=condition,
            category_id=str(raw.get("catalog_id") or catalog.get("id") or "") or None,
            category_name=_value_title(catalog) or (category_path[-1] if category_path else None),
            category_path=category_path,
            colors=colors,
            published_at=raw.get("created_at") or raw.get("published_at"),
            favourite_count=raw.get("favourite_count"),
            view_count=raw.get("view_count"),
            shipping=None,
            status=status,
            seller={
                "id": seller.get("id"),
                "name": seller.get("login") or seller.get("name"),
                "rating": seller.get("feedback_reputation") or seller.get("rating"),
                "reviews_count": seller.get("feedback_count") or seller.get("reviews_count"),
                "location": seller.get("city") or seller.get("country_title"),
                "created_at": seller.get("created_at"),
                "last_login_at": seller.get("last_logged_on_ts"),
            },
            source_url=source_url,
        )

    async def _search_jsonld(self, params: list[tuple[str, Any]]) -> list[dict[str, Any]]:
        url = self.base + "/catalog"
        response = await self.http.get(
            url,
            params=params,
            headers={"Accept": "text/html,application/xhtml+xml"},
            timeout=20,
        )
        full_url = f"{url}?{urlencode(params)}"
        body = response.text[:4000] if response.status_code >= 400 else None
        self._record(RequestDiagnostics(
            url=full_url,
            headers=("Accept",),
            status_code=response.status_code,
            response_body=body,
            fallback_used=True,
        ))
        if response.status_code >= 400:
            return []
        return extract_jsonld_items(response.text)
