import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import SessionLocal
from app.models import Alert, Listing, ListingProductMatch, ListingSnapshot, ListingStatus, PriceStat, Product
from app.notifications import notify
from app.normalizer import normalize
from app.pricing import Score, robust_score
from app.vinted import VintedClient


Notifier = Callable[[Listing, str], Awaitable[None]]
THRESHOLD_RANK = {"DEAL": 0, "GOOD": 1, "NORMAL": 2, "EXPENSIVE": 3}


def allowed(item: dict, alert: Alert) -> bool:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    if alert.exclude_terms and any(term.lower() in text for term in alert.exclude_terms):
        return False
    return not alert.include_terms or any(term.lower() in text for term in alert.include_terms)


def score_reaches_threshold(score: Score | None, threshold: str) -> bool:
    if score is None:
        return False
    score_rank = THRESHOLD_RANK.get(score.label)
    threshold_rank = THRESHOLD_RANK.get(threshold.upper())
    return score_rank is not None and threshold_rank is not None and score_rank <= threshold_rank


def alert_is_due(alert: Alert, now: datetime | None = None) -> bool:
    if alert.paused:
        return False
    if alert.last_scan_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    last_scan = alert.last_scan_at
    if last_scan.tzinfo is None:
        last_scan = last_scan.replace(tzinfo=timezone.utc)
    return current - last_scan >= timedelta(minutes=max(1, alert.scan_minutes))


def _amount(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("amount") or value.get("price") or value.get("value")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _currency(item: dict) -> str:
    price = item.get("price")
    if isinstance(price, dict):
        return str(price.get("currency_code") or price.get("currency") or "EUR")
    return str(item.get("currency") or "EUR")


def _first_amount(item: dict, *keys: str) -> float:
    for key in keys:
        if key in item and item[key] is not None:
            return _amount(item[key])
    return 0


def _photo_url(item: dict) -> str | None:
    urls = _photo_urls(item)
    return urls[0] if urls else None


def _photo_urls(item: dict) -> list[str]:
    urls: list[str] = []
    photo = item.get("photo")
    if isinstance(photo, dict):
        url = photo.get("url") or photo.get("full_size_url")
        if url:
            urls.append(str(url))
    photos = item.get("photos")
    if isinstance(photos, list):
        for candidate in photos:
            if isinstance(candidate, dict):
                url = candidate.get("url") or candidate.get("full_size_url")
            else:
                url = candidate
            if url and str(url) not in urls:
                urls.append(str(url))
    if not urls and photo:
        urls.append(str(photo))
    return urls


def _seller(item: dict) -> tuple[str | None, float | None, int | None]:
    seller = item.get("user") or item.get("seller") or {}
    if not isinstance(seller, dict):
        return None, None, None
    name = seller.get("login") or seller.get("username") or seller.get("name")
    rating = seller.get("feedback_reputation") or seller.get("rating")
    reviews = seller.get("feedback_count") or seller.get("reviews_count")
    try:
        parsed_rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        parsed_rating = None
    try:
        parsed_reviews = int(reviews) if reviews is not None else None
    except (TypeError, ValueError):
        parsed_reviews = None
    return str(name) if name else None, parsed_rating, parsed_reviews


def _text_attribute(item: dict, *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("title") or value.get("name")
        if value:
            return str(value)
    return None


def _apply_score(listing: Listing, score: Score | None) -> None:
    listing.score_label = score.label if score else None
    listing.score_percentile = score.percentile if score else None
    listing.score_median = score.median if score else None
    listing.score_sample_count = score.count if score else 0
    listing.score_confidence = score.confidence if score else None


async def scan(
    alert: Alert,
    client: VintedClient,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    notifier: Notifier = notify,
) -> int:
    items = [item for item in await client.search(alert) if allowed(item, alert)]
    candidates = []
    for item in items:
        price = _amount(item.get("price"))
        buyer_fee = _first_amount(item, "service_fee", "service_fee_amount", "buyer_fee")
        shipping = _first_amount(item, "shipping_fee", "shipping_price", "shipping_estimate")
        if price > 0 and item.get("id") is not None:
            normalized = normalize(str(item.get("title") or ""), str(item.get("description") or ""))
            candidates.append((item, price, buyer_fee, shipping, normalized))
    notifications: list[tuple[Listing, str]] = []

    async with session_factory() as db:
        database_alert = await db.get(Alert, alert.id)
        if database_alert is None:
            return 0
        persisted_prices = list(
            await db.scalars(
                select(Listing.price + Listing.buyer_fee + Listing.shipping_estimate).where(
                    Listing.alert_id == alert.id,
                    Listing.price > 0,
                )
            )
        )
        current_prices = [price + buyer_fee + shipping for _, price, buyer_fee, shipping, _ in candidates]
        comparison_pool = current_prices if len(current_prices) >= 4 else persisted_prices + current_prices
        baseline_scan = database_alert.last_scan_at is None
        products: dict[str, Product] = {}

        for item, price, buyer_fee, shipping, normalized in candidates:
            external_id = str(item["id"])
            product = products.get(normalized.key)
            if product is None:
                product = await db.scalar(select(Product).where(Product.canonical_key == normalized.key))
                if product is None:
                    product = Product(
                        canonical_key=normalized.key,
                        brand=normalized.brand,
                        model=normalized.model,
                        attributes={"flags": sorted(normalized.flags)},
                    )
                    db.add(product)
                    await db.flush()
                products[normalized.key] = product
            listing = await db.scalar(
                select(Listing).where(
                    Listing.alert_id == alert.id,
                    Listing.external_id == external_id,
                )
            )
            comparables = comparison_pool.copy()
            try:
                comparables.remove(price + buyer_fee + shipping)
            except ValueError:
                pass
            score = robust_score(price + buyer_fee + shipping, comparables)
            seller_name, seller_rating, seller_reviews = _seller(item)
            photos = _photo_urls(item)

            if listing is None:
                listing = Listing(
                    alert_id=alert.id,
                    external_id=external_id,
                    title=str(item.get("title") or "Annonce Vinted"),
                    description=str(item.get("description") or ""),
                    price=price,
                    buyer_fee=buyer_fee,
                    shipping_estimate=shipping,
                    currency=_currency(item),
                    url=str(item.get("url") or f"{settings.vinted_domain}/items/{external_id}"),
                    image_url=_photo_url(item),
                    image_urls=photos,
                    seller_name=seller_name,
                    seller_rating=seller_rating,
                    seller_reviews_count=seller_reviews,
                    condition=_text_attribute(item, "status", "condition"),
                    size=_text_attribute(item, "size", "size_title"),
                    status=ListingStatus.ACTIVE,
                )
                _apply_score(listing, score)
                db.add(listing)
                await db.flush()
                db.add(
                    ListingProductMatch(
                        listing_id=listing.id,
                        product_id=product.id,
                        confidence=1.0 if normalized.brand and normalized.model else 0.5,
                    )
                )
                db.add(
                    ListingSnapshot(
                        listing_id=listing.id,
                        price=price,
                        status=ListingStatus.ACTIVE,
                    )
                )
                if not baseline_scan and score_reaches_threshold(score, database_alert.notify_threshold):
                    notifications.append((listing, score.label))
            else:
                changed = (
                    listing.price != price
                    or listing.buyer_fee != buyer_fee
                    or listing.shipping_estimate != shipping
                    or listing.status != ListingStatus.ACTIVE
                )
                listing.title = str(item.get("title") or listing.title)
                listing.description = str(item.get("description") or listing.description)
                listing.url = str(item.get("url") or listing.url)
                listing.image_url = _photo_url(item) or listing.image_url
                listing.image_urls = photos or listing.image_urls
                listing.seller_name = seller_name or listing.seller_name
                listing.seller_rating = seller_rating if seller_rating is not None else listing.seller_rating
                listing.seller_reviews_count = seller_reviews if seller_reviews is not None else listing.seller_reviews_count
                listing.condition = _text_attribute(item, "status", "condition") or listing.condition
                listing.size = _text_attribute(item, "size", "size_title") or listing.size
                listing.currency = _currency(item)
                listing.price = price
                listing.buyer_fee = buyer_fee
                listing.shipping_estimate = shipping
                listing.status = ListingStatus.ACTIVE
                listing.updated_at = datetime.now(timezone.utc)
                _apply_score(listing, score)
                if changed:
                    db.add(ListingSnapshot(listing_id=listing.id, price=price, status=ListingStatus.ACTIVE))

            match = await db.get(ListingProductMatch, listing.id)
            if match is None:
                db.add(
                    ListingProductMatch(
                        listing_id=listing.id,
                        product_id=product.id,
                        confidence=1.0 if normalized.brand and normalized.model else 0.5,
                    )
                )
            else:
                match.product_id = product.id
                match.confidence = 1.0 if normalized.brand and normalized.model else 0.5

        for key, product in products.items():
            values = sorted(
                price + buyer_fee + shipping
                for _, price, buyer_fee, shipping, normalized in candidates
                if normalized.key == key
            )
            if len(values) < 3:
                continue
            statistic = await db.scalar(
                select(PriceStat).where(PriceStat.product_id == product.id, PriceStat.condition == "ALL")
            )
            if statistic is None:
                statistic = PriceStat(product_id=product.id, condition="ALL")
                db.add(statistic)
            statistic.median = median(values)
            statistic.p20 = values[int((len(values) - 1) * 0.20)]
            statistic.p75 = values[int((len(values) - 1) * 0.75)]
            statistic.sample_count = len(values)
            statistic.window_days = 60

        database_alert.last_scan_at = datetime.now(timezone.utc)
        await db.commit()

    for listing, label in notifications:
        await notifier(listing, label)
    return len(candidates)


async def run() -> None:
    client = VintedClient()
    while True:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as db:
            alerts = list(await db.scalars(select(Alert).where(Alert.paused.is_(False))))
        for alert in alerts:
            if not alert_is_due(alert, now):
                continue
            try:
                count = await scan(alert, client)
                print(f"scan alert={alert.id} items={count}")
            except Exception as error:
                print(f"scan alert={alert.id} error={error}")
            await asyncio.sleep(max(15, 60 / settings.scan_global_rpm) + random.uniform(1, 8))
        await asyncio.sleep(20)


if __name__ == "__main__":
    asyncio.run(run())
