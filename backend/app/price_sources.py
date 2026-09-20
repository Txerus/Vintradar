import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from xml.etree import ElementTree

import httpx

from app.config import settings


@dataclass(frozen=True)
class ExternalQuote:
    source: str
    value: float
    currency: str
    meta: dict


class PriceSource(ABC):
    @abstractmethod
    async def quote(self, canonical_key: str, condition: str) -> ExternalQuote | None:
        ...


class TimedCache:
    def __init__(self, ttl_hours: int = 24) -> None:
        self.ttl = timedelta(hours=ttl_hours)
        self.values: dict[str, tuple[datetime, object]] = {}

    def get(self, key: str):
        hit = self.values.get(key)
        if hit and datetime.now(timezone.utc) - hit[0] < self.ttl:
            return hit[1]
        return None

    def put(self, key: str, value: object) -> object:
        self.values[key] = (datetime.now(timezone.utc), value)
        return value


class RebrickableValidator:
    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.rebrickable_api_key
        self.client = client
        self.cache = TimedCache()

    async def validate(self, set_number: str) -> dict | None:
        if not self.api_key:
            return None
        if (cached := self.cache.get(set_number)) is not None:
            return cached or None
        owns = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            response = await client.get(
                f"https://rebrickable.com/api/v3/lego/sets/{set_number}-1/",
                headers={"Authorization": f"key {self.api_key}"},
                timeout=15,
            )
            if response.status_code == 404:
                self.cache.put(set_number, {})
                return {}
            response.raise_for_status()
            return self.cache.put(set_number, response.json())
        finally:
            if owns:
                await client.aclose()


def _oauth_header(method: str, url: str, credentials: dict[str, str], query: dict[str, str]) -> str:
    oauth = {
        "oauth_consumer_key": credentials["consumer_key"],
        "oauth_token": credentials["token"],
        "oauth_nonce": secrets.token_hex(12),
        "oauth_timestamp": str(int(time.time())),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
    }
    parameters = list(parse_qsl(urlparse(url).query)) + list(query.items()) + list(oauth.items())
    parameters.sort()
    normalized = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in parameters)
    base_url = url.split("?", 1)[0]
    signature_base = "&".join(quote(value, safe="") for value in (method.upper(), base_url, normalized))
    key = f"{quote(credentials['consumer_secret'], safe='')}&{quote(credentials['token_secret'], safe='')}"
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key.encode(), signature_base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(f'{key}="{quote(value, safe="")}"' for key, value in sorted(oauth.items()))


class BrickLinkSource(PriceSource):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self.cache = TimedCache()
        values = (
            settings.bricklink_consumer_key, settings.bricklink_consumer_secret,
            settings.bricklink_token_value, settings.bricklink_token_secret,
        )
        self.credentials = dict(zip(("consumer_key", "consumer_secret", "token", "token_secret"), values)) if all(values) else None

    async def quote(self, canonical_key: str, condition: str) -> ExternalQuote | None:
        if not self.credentials or not canonical_key.startswith("lego:"):
            return None
        cache_key = f"{canonical_key}:{condition}"
        if (cached := self.cache.get(cache_key)) is not None:
            return cached
        number = canonical_key.split(":", 1)[1]
        query = {
            "new_or_used": "N" if condition.startswith("NEW") else "U",
            "guide_type": "sold", "region": "europe", "currency_code": "EUR",
        }
        url = f"https://api.bricklink.com/api/store/v1/items/SET/{number}-1/price"
        headers = {"Authorization": _oauth_header("GET", url, self.credentials, query)}
        owns = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            response = await client.get(url, params=query, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json().get("data") or {}
            value = float(data.get("avg_price") or 0)
            quote_value = ExternalQuote("bricklink_sold_europe", value, "EUR", data) if value else None
            return self.cache.put(cache_key, quote_value)
        finally:
            if owns:
                await client.aclose()


class BricksetSource(PriceSource):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self.cache = TimedCache()

    async def set_info(self, number: str) -> dict | None:
        if not settings.brickset_api_key:
            return None
        if (cached := self.cache.get(number)) is not None:
            return cached
        owns = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            response = await client.get(
                "https://brickset.com/api/v3.asmx/getSets",
                params={"apiKey": settings.brickset_api_key, "userHash": "", "params": f'{{"setNumber":"{number}"}}'},
                timeout=20,
            )
            response.raise_for_status()
            matches = response.json().get("sets") or []
            if not matches:
                return self.cache.put(number, None)
            return self.cache.put(number, matches[0])
        finally:
            if owns:
                await client.aclose()

    async def quote(self, canonical_key: str, condition: str) -> ExternalQuote | None:
        if not canonical_key.startswith("lego:"):
            return None
        number = canonical_key.split(":", 1)[1]
        data = await self.set_info(number)
        if data:
            value = float(((data.get("LEGOCom") or {}).get("retailPrice") or 0))
            return ExternalQuote("brickset_retail", value, "EUR", data) if value else None
        return None


class ECBRates:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self.cache = TimedCache()

    async def usd_to_eur(self) -> float:
        if (cached := self.cache.get("USD")) is not None:
            return float(cached)
        owns = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            response = await client.get(
                "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
                timeout=20,
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            usd = next(float(node.attrib["rate"]) for node in root.iter() if node.attrib.get("currency") == "USD")
            return float(self.cache.put("USD", 1 / usd))
        finally:
            if owns:
                await client.aclose()


class PriceChartingSource(PriceSource):
    def __init__(self, client: httpx.AsyncClient | None = None, rates: ECBRates | None = None) -> None:
        self.client = client
        self.rates = rates or ECBRates(client)
        self.cache = TimedCache()
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _get(self, url: str, params: dict) -> dict:
        async with self._lock:
            delay = 1 - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            owns = self.client is None
            client = self.client or httpx.AsyncClient()
            try:
                response = await client.get(url, params=params, timeout=20)
                self._last_request = time.monotonic()
                response.raise_for_status()
                return response.json()
            finally:
                if owns:
                    await client.aclose()

    async def quote(self, canonical_key: str, condition: str) -> ExternalQuote | None:
        if not settings.pricecharting_token or not canonical_key.startswith(("game:", "console:")):
            return None
        cache_key = f"{canonical_key}:{condition}"
        if (cached := self.cache.get(cache_key)) is not None:
            return cached
        parts = canonical_key.split(":")
        query = " ".join(parts[1:]).replace("-", " ")
        if canonical_key.startswith("console:"):
            query = f"PAL {query}"
        search = await self._get(
            "https://www.pricecharting.com/api/products",
            {"t": settings.pricecharting_token, "q": query},
        )
        products = search.get("products") or []
        if not products:
            return self.cache.put(cache_key, None)
        product = await self._get(
            "https://www.pricecharting.com/api/product",
            {"t": settings.pricecharting_token, "id": products[0]["id"]},
        )
        if condition.startswith(("NEW_WITH_TAGS", "NEW_WITHOUT_TAGS")):
            field = "new-price"
        elif "BOX_ONLY" in condition:
            field = "box-only-price"
        elif "LOOSE" in condition:
            field = "loose-price"
        else:
            field = "cib-price"
        cents = float(product.get(field) or 0)
        if not cents:
            return self.cache.put(cache_key, None)
        rate = await self.rates.usd_to_eur()
        result = ExternalQuote(
            "pricecharting", round(cents / 100 * rate, 2), "EUR",
            {"field": field, "usd_cents": cents, "product": product.get("product-name"), "indicative": True},
        )
        return self.cache.put(cache_key, result)
