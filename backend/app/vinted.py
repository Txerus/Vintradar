import asyncio
import hashlib
import html
import json
import random
import re
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

    def _record(self, diagnostics: RequestDiagnostics) -> None:
        self.last_diagnostics = diagnostics
        self.request_history.append(diagnostics)

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

    async def search(self, alert: Any) -> list[dict[str, Any]]:
        self.request_history = []
        if not self.ready:
            await self.bootstrap()
        params = self.search_params(alert)
        api_url = self.api_base + "/svc-catalogue/items"
        last_error: str | None = None
        for attempt in range(4):
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
