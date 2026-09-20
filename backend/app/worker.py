import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Alert, AlertListing, Listing, ListingProductMatch, ListingSnapshot, ListingStatus,
    PriceStat, Product, SellerProfile, WorkerState,
)
from app.normalizer import Normalized, condition_segment, fold, normalize
from app.notifications import notify
from app.price_sources import BrickLinkSource, BricksetSource, PriceChartingSource, RebrickableValidator
from app.pricing import Comparable, Score, explanation, score_listing
from app.vinted import ItemDetail, VintedClient, VintedError


Notifier = Callable[[Listing, str], Awaitable[None]]
THRESHOLD_RANK = {"DEAL": 0, "GOOD": 1, "NORMAL": 2, "EXPENSIVE": 3}


def _words(value: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z0-9]+", fold(value)))


def allowed(item: dict, alert: Alert) -> bool:
    words = _words(f"{item.get('title', '')} {item.get('description', '')}")
    excluded = [_words(term) for term in alert.exclude_terms]
    included = [_words(term) for term in alert.include_terms]
    if any(term_words and term_words <= words for term_words in excluded):
        return False
    return not included or any(term_words and term_words <= words for term_words in included)


def score_reaches_threshold(score: Score | None, threshold: str) -> bool:
    threshold = threshold.upper()
    if threshold == "ALL":
        return True
    if score is None:
        return False
    score_rank = THRESHOLD_RANK.get(score.label)
    threshold_rank = THRESHOLD_RANK.get(threshold)
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
    return current - last_scan >= timedelta(minutes=max(2, alert.scan_minutes))


def _amount(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("amount") or value.get("price") or value.get("value")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _first_amount(item: dict, *keys: str) -> float:
    for key in keys:
        if key in item and item[key] is not None:
            return _amount(item[key])
    return 0


def _currency(item: dict) -> str:
    for key in ("total_item_price", "price"):
        value = item.get(key)
        if isinstance(value, dict):
            return str(value.get("currency_code") or value.get("currency") or "EUR")
    return str(item.get("currency") or "EUR")


def _photo_urls(item: dict) -> list[str]:
    values: list[str] = []
    for photo in [item.get("photo")] + list(item.get("photos") or []):
        if isinstance(photo, dict):
            url = photo.get("full_size_url") or photo.get("url")
        else:
            url = photo
        if url and str(url) not in values:
            values.append(str(url))
    return values


def _text_attribute(item: dict, *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("title") or value.get("name")
        if value:
            return str(value)
    return None


def _catalog_summary(item: dict) -> tuple[str | None, str | None, str | None, str | None]:
    item_box = item.get("item_box") if isinstance(item.get("item_box"), dict) else {}
    parts = [part.strip() for part in str(item_box.get("second_line") or "").split("·") if part.strip()]
    size = _text_attribute(item, "size", "size_title") or (parts[0] if parts else None)
    condition = _text_attribute(item, "status", "condition") or (parts[-1] if len(parts) > 1 else None)
    brand = _text_attribute(item, "brand") or item_box.get("first_line")
    catalog = item.get("catalog") if isinstance(item.get("catalog"), dict) else {}
    category_id = str(item.get("catalog_id") or catalog.get("id") or "") or None
    return size, condition, str(brand) if brand else None, category_id


def _seller_summary(item: dict) -> tuple[str | None, str | None, float | None, int | None]:
    seller = item.get("user") or item.get("seller") or {}
    if not isinstance(seller, dict):
        return None, None, None, None
    def number(key: str, cast):
        try:
            return cast(seller[key]) if seller.get(key) is not None else None
        except (TypeError, ValueError):
            return None
    identifier = seller.get("id") or item.get("user_id")
    return (
        str(identifier) if identifier else None,
        seller.get("login") or seller.get("username") or seller.get("name"),
        number("feedback_reputation", float) or number("rating", float),
        number("feedback_count", int) or number("reviews_count", int),
    )


def _absolute_url(value: Any, external_id: str) -> str:
    raw = str(value or f"/items/{external_id}")
    return urljoin(settings.vinted_domain.rstrip("/") + "/", raw)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _apply_detail(listing: Listing, detail: ItemDetail) -> None:
    listing.title = detail.title or listing.title
    listing.description = detail.description or listing.description
    listing.image_urls = detail.photos or listing.image_urls
    listing.image_url = listing.image_urls[0] if listing.image_urls else listing.image_url
    listing.brand = detail.brand or listing.brand
    listing.size = detail.size or listing.size
    listing.condition = detail.condition or listing.condition
    listing.condition_segment = condition_segment(listing.condition)
    listing.category_id = detail.category_id or listing.category_id
    listing.category_name = detail.category_name or listing.category_name
    listing.category_path = detail.category_path or listing.category_path
    listing.colors = detail.colors or listing.colors
    listing.published_at = _parse_datetime(detail.published_at) or listing.published_at
    listing.favourite_count = detail.favourite_count
    listing.view_count = detail.view_count
    if detail.shipping is not None:
        listing.shipping_estimate = detail.shipping
    seller = detail.seller
    listing.seller_id = str(seller.get("id")) if seller.get("id") else listing.seller_id
    listing.seller_name = seller.get("name") or listing.seller_name
    listing.seller_rating = seller.get("rating") if seller.get("rating") is not None else listing.seller_rating
    listing.seller_reviews_count = seller.get("reviews_count") if seller.get("reviews_count") is not None else listing.seller_reviews_count
    listing.seller_location = seller.get("location") or listing.seller_location
    listing.seller_created_at = _parse_datetime(seller.get("created_at")) or listing.seller_created_at
    listing.seller_last_login_at = _parse_datetime(seller.get("last_login_at")) or listing.seller_last_login_at
    listing.enriched_at = datetime.now(timezone.utc)
    listing.enrichment_price = listing.price
    if detail.status in ListingStatus.__members__:
        listing.status = ListingStatus[detail.status]


async def _normalization(listing: Listing, validator: RebrickableValidator) -> Normalized:
    provisional = normalize(
        listing.title, listing.description, brand=listing.brand,
        category=listing.category_name or listing.category_id, size=listing.size,
    )
    if provisional.key and provisional.key.startswith("lego:") and (validator.api_key or settings.brickset_api_key):
        number = provisional.key.split(":", 1)[1]
        validation = await validator.validate(number) if validator.api_key else await BricksetSource().set_info(number)
        return normalize(
            listing.title, listing.description, brand=listing.brand,
            category=listing.category_name or listing.category_id, size=listing.size,
            lego_validated=bool(validation),
        )
    return provisional


async def _match_product(db: AsyncSession, listing: Listing, normalized: Normalized) -> Product | None:
    match = await db.get(ListingProductMatch, listing.id)
    if match and match.manual:
        return await db.get(Product, match.product_id) if match.product_id else None
    product = None
    if normalized.key:
        product = await db.scalar(select(Product).where(Product.canonical_key == normalized.key))
        if product is None:
            product = Product(
                canonical_key=normalized.key, brand=normalized.brand, model=normalized.model,
                category_key=normalized.category_key,
                attributes={**normalized.attributes, "flags": sorted(normalized.flags)},
            )
            db.add(product)
            await db.flush()
    if match is None:
        match = ListingProductMatch(listing_id=listing.id)
        db.add(match)
    match.product_id = product.id if product else None
    match.confidence = normalized.confidence
    match.recognized_text = normalized.recognized_text
    match.excluded_from_stats = bool(normalized.flags & {"LOT", "PARTS", "BROKEN", "EMPTY_BOX", "MANUAL_ONLY"})
    return product


async def _all_comparables(db: AsyncSession) -> tuple[list[Comparable], dict[int, tuple[ListingProductMatch, Product | None]]]:
    rows = (await db.execute(
        select(Listing, ListingProductMatch, Product)
        .join(ListingProductMatch, ListingProductMatch.listing_id == Listing.id)
        .outerjoin(Product, Product.id == ListingProductMatch.product_id)
    )).all()
    values: list[Comparable] = []
    mapping: dict[int, tuple[ListingProductMatch, Product | None]] = {}
    for listing, match, product in rows:
        mapping[listing.id] = (match, product)
        flags = frozenset((product.attributes if product else {}).get("flags") or [])
        if match.excluded_from_stats:
            flags = flags | {"PARTS"}
        values.append(Comparable(
            id=listing.id, external_id=listing.external_id,
            product_key=product.canonical_key if product else "",
            brand=product.brand if product else listing.brand,
            category_key=product.category_key if product else listing.category_id,
            condition_segment=listing.condition_segment,
            total_price=listing.total_item_price, title=listing.title,
            seller_id=listing.seller_id, status=listing.status.value,
            first_seen_at=listing.first_seen_at, flags=flags,
            image_url=listing.image_url, url=listing.url,
        ))
    return values, mapping


async def _score_and_explain(db: AsyncSession, listing: Listing) -> Score | None:
    values, matches = await _all_comparables(db)
    target = next(value for value in values if value.id == listing.id)
    match, product = matches[listing.id]
    if not product or match.confidence < .4 or not listing.condition_segment:
        reason = "catégorie, produit ou état non reconnu avec assez de confiance"
        listing.pricing_explanation = explanation(
            target, None, price=listing.price, buyer_fee=listing.buyer_fee,
            shipping=listing.shipping_estimate,
            recognition={"key": product.canonical_key if product else None, "confidence": match.confidence, "text": match.recognized_text},
        )
        listing.pricing_explanation["reason"] = reason
        score = None
    else:
        score = score_listing(target, values)
        references = []
        product_flags = set(product.attributes.get("flags") or [])
        source_condition = listing.condition_segment
        if "LOOSE" in product_flags:
            source_condition += ":LOOSE"
        if "EMPTY_BOX" in product_flags:
            source_condition += ":BOX_ONLY"
        for source in (BrickLinkSource(), BricksetSource(), PriceChartingSource()):
            try:
                quote = await source.quote(product.canonical_key, source_condition)
            except Exception as error:
                references.append({"source": type(source).__name__, "error": type(error).__name__})
                continue
            if quote:
                references.append({"source": quote.source, "value": quote.value, "currency": quote.currency, "meta": quote.meta})
        if score and any(
            reference.get("value") and abs(reference["value"] / score.median - 1) > .40
            for reference in references
        ):
            from dataclasses import replace
            score = replace(score, confidence="LOW")
        listing.pricing_explanation = explanation(
            target, score, price=listing.price, buyer_fee=listing.buyer_fee,
            shipping=listing.shipping_estimate,
            recognition={"key": product.canonical_key, "model": product.model, "confidence": match.confidence, "text": match.recognized_text},
            external_references=references,
        )
    listing.score_label = score.label if score else None
    listing.score_percentile = score.percentile if score else None
    listing.score_median = score.median if score else None
    listing.score_sample_count = score.count if score else 0
    listing.score_confidence = score.confidence if score else None
    if score and product:
        stat = await db.scalar(select(PriceStat).where(
            PriceStat.product_id == product.id, PriceStat.condition == listing.condition_segment,
        ))
        if stat is None:
            stat = PriceStat(product_id=product.id, condition=listing.condition_segment)
            db.add(stat)
        stat.median, stat.p20, stat.p75 = score.median, score.p20, score.p75
        stat.sample_count, stat.window_days = score.count, 90
        stat.computed_at = datetime.now(timezone.utc)
    return score


async def _search_pages(client: VintedClient, alert: Alert, pages: int) -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, pages + 1):
        try:
            page_items = await client.search(alert, page=page)
        except TypeError:
            page_items = await client.search(alert)
            pages = 1
        for item in page_items:
            if item.get("id") is not None:
                items[str(item["id"])] = item
        if pages == 1:
            break
    return list(items.values())


async def _targeted_collect(
    db: AsyncSession,
    client: VintedClient,
    alert: Alert,
    products: list[Product],
    validator: RebrickableValidator,
) -> int:
    collected = 0
    now = datetime.now(timezone.utc)
    for product in {value.id: value for value in products if value}.values():
        targeted_at = product.targeted_at
        if targeted_at and targeted_at.tzinfo is None:
            targeted_at = targeted_at.replace(tzinfo=timezone.utc)
        if targeted_at and now - targeted_at < timedelta(hours=24):
            continue
        known = await db.scalar(select(func.count()).select_from(ListingProductMatch).where(
            ListingProductMatch.product_id == product.id,
            ListingProductMatch.excluded_from_stats.is_(False),
        ))
        if (known or 0) >= 6:
            continue
        query = " ".join(filter(None, [product.brand, product.model]))
        try:
            items = await client.search(alert, page=1, search_text=query)
        except (TypeError, VintedError):
            product.targeted_at = now
            continue
        for item in items:
            external_id = str(item.get("id") or "")
            if not external_id or await db.scalar(select(Listing.id).where(Listing.external_id == external_id)):
                continue
            size, condition, brand, category_id = _catalog_summary(item)
            provisional = normalize(
                str(item.get("title") or ""), str(item.get("description") or ""),
                brand=brand, category=category_id, size=size,
            )
            if provisional.key != product.canonical_key:
                continue
            price = _amount(item.get("price"))
            fee = _first_amount(item, "service_fee", "service_fee_amount", "buyer_fee")
            total = _first_amount(item, "total_item_price") or price + fee
            if total <= 0:
                continue
            photos = _photo_urls(item)
            seller_id, seller_name, seller_rating, seller_reviews = _seller_summary(item)
            listing = Listing(
                external_id=external_id, title=str(item.get("title") or "Annonce Vinted"),
                description=str(item.get("description") or ""), price=price, total_item_price=total,
                buyer_fee=fee, shipping_estimate=0, currency=_currency(item),
                url=f"https://www.vinted.fr/items/{external_id}", image_url=photos[0] if photos else None,
                image_urls=photos, brand=brand, category_id=category_id,
                seller_id=seller_id, seller_name=seller_name, seller_rating=seller_rating,
                seller_reviews_count=seller_reviews, condition=condition,
                condition_segment=condition_segment(condition), size=size, status=ListingStatus.ACTIVE,
            )
            db.add(listing)
            await db.flush()
            await _match_product(db, listing, await _normalization(listing, validator))
            db.add(ListingSnapshot(
                listing_id=listing.id, price=price, total_item_price=total, status=listing.status,
            ))
            collected += 1
        product.targeted_at = now
    return collected


async def scan(
    alert: Alert,
    client: VintedClient,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    notifier: Notifier = notify,
    validator: RebrickableValidator | None = None,
) -> int:
    started = time.monotonic()
    validator = validator or RebrickableValidator()
    baseline = alert.last_scan_at is None
    raw_items = await _search_pages(client, alert, 5 if baseline else 1)
    notifications: list[tuple[Listing, str]] = []
    received_ids: set[str] = set()
    enriched = errors = 0
    new_links: list[tuple[Listing, AlertListing]] = []
    async with session_factory() as status_db:
        state = await status_db.get(WorkerState, 1)
        if state is None:
            state = WorkerState(id=1)
            status_db.add(state)
        state.enrichment_queue_size = sum(1 for item in raw_items if allowed(item, alert))
        await status_db.commit()
    async with session_factory() as db:
        database_alert = await db.get(Alert, alert.id)
        if database_alert is None:
            return 0
        for item in raw_items:
            if not allowed(item, database_alert) or item.get("id") is None:
                continue
            external_id = str(item["id"])
            received_ids.add(external_id)
            price = _amount(item.get("price"))
            fee = _first_amount(item, "service_fee", "service_fee_amount", "buyer_fee")
            total = _first_amount(item, "total_item_price") or price + fee
            if price <= 0 or total <= 0:
                continue
            listing = await db.scalar(select(Listing).where(Listing.external_id == external_id))
            is_new_listing = listing is None
            size, condition, brand, category_id = _catalog_summary(item)
            seller_id, seller_name, seller_rating, seller_reviews = _seller_summary(item)
            photos = _photo_urls(item)
            if listing is None:
                listing = Listing(
                    external_id=external_id, title=str(item.get("title") or "Annonce Vinted"),
                    description=str(item.get("description") or ""), price=price, total_item_price=total,
                    buyer_fee=fee, shipping_estimate=_first_amount(item, "shipping_fee", "shipping_price", "shipping_estimate"),
                    currency=_currency(item), url=f"https://www.vinted.fr/items/{external_id}",
                    image_url=photos[0] if photos else None, image_urls=photos, brand=brand,
                    category_id=category_id, seller_id=seller_id, seller_name=seller_name,
                    seller_rating=seller_rating, seller_reviews_count=seller_reviews,
                    condition=condition, condition_segment=condition_segment(condition), size=size,
                    favourite_count=item.get("favourite_count"), status=ListingStatus.ACTIVE,
                )
                db.add(listing)
                await db.flush()
            link = await db.get(AlertListing, (database_alert.id, listing.id))
            if link is None:
                link = AlertListing(alert_id=database_alert.id, listing_id=listing.id)
                db.add(link)
                new_links.append((listing, link))
            changed = listing.price != price or listing.total_item_price != total or listing.status != ListingStatus.ACTIVE
            listing.price, listing.total_item_price, listing.buyer_fee = price, total, fee
            listing.currency = _currency(item)
            listing.url = f"https://www.vinted.fr/items/{external_id}"
            listing.status = ListingStatus.ACTIVE
            listing.updated_at = datetime.now(timezone.utc)
            if is_new_listing or listing.enriched_at is None or listing.enrichment_price != price:
                try:
                    detail = await client.detail(external_id)
                    _apply_detail(listing, detail)
                    enriched += 1
                    if listing.seller_id:
                        profile = await db.get(SellerProfile, listing.seller_id)
                        if profile is None:
                            db.add(SellerProfile(seller_id=listing.seller_id, payload=detail.seller))
                        elif datetime.now(timezone.utc) - profile.fetched_at.replace(tzinfo=profile.fetched_at.tzinfo or timezone.utc) >= timedelta(hours=24):
                            profile.payload, profile.fetched_at = detail.seller, datetime.now(timezone.utc)
                except (VintedError, Exception):
                    errors += 1
            # Description exclusions are deliberately applied after enrichment.
            if not allowed({"title": listing.title, "description": listing.description}, database_alert):
                await db.delete(link)
                continue
            normalized = await _normalization(listing, validator)
            await _match_product(db, listing, normalized)
            if is_new_listing or changed:
                db.add(ListingSnapshot(
                    listing_id=listing.id, price=listing.price, total_item_price=listing.total_item_price,
                    favourite_count=listing.favourite_count, view_count=listing.view_count, status=listing.status,
                ))
            await db.flush()

        # A missing followed listing is checked individually; absence alone never decides its status.
        linked = list(await db.scalars(
            select(Listing).join(AlertListing, AlertListing.listing_id == Listing.id).where(
                AlertListing.alert_id == database_alert.id, Listing.status.in_([ListingStatus.ACTIVE, ListingStatus.RESERVED]),
            )
        ))
        for missing in [value for value in linked if value.external_id not in received_ids][:3]:
            try:
                detail = await client.detail(missing.external_id)
                _apply_detail(missing, detail)
                missing.status_checked_at = datetime.now(timezone.utc)
                if detail.status == "RESERVED":
                    missing.status = ListingStatus.SOLD_CONFIRMED
            except VintedError:
                missing.status = ListingStatus.DISAPPEARED
                errors += 1
            db.add(ListingSnapshot(
                listing_id=missing.id, price=missing.price, total_item_price=missing.total_item_price,
                favourite_count=missing.favourite_count, view_count=missing.view_count, status=missing.status,
            ))

        new_products: list[Product] = []
        for listing, _ in new_links:
            match = await db.get(ListingProductMatch, listing.id)
            if match and match.product_id:
                product = await db.get(Product, match.product_id)
                if product:
                    new_products.append(product)
        await _targeted_collect(db, client, database_alert, new_products, validator)

        for listing, link in new_links:
            score = await _score_and_explain(db, listing)
            if not baseline and score_reaches_threshold(score, database_alert.notify_threshold):
                notifications.append((listing, score.label if score else "UNEVALUATED"))
                link.notified_at = datetime.now(timezone.utc)
        database_alert.last_scan_at = datetime.now(timezone.utc)
        database_alert.bootstrap_pages_done = 5 if baseline else database_alert.bootstrap_pages_done
        state = await db.get(WorkerState, 1)
        if state is None:
            state = WorkerState(id=1)
            db.add(state)
        state.last_scan_at = database_alert.last_scan_at
        state.last_error = None
        history = getattr(client, "request_history", [])
        state.recent_403_count = sum(1 for value in history if value.status_code == 403)
        state.recent_429_count = sum(1 for value in history if value.status_code == 429)
        state.enrichment_queue_size = 0
        await db.commit()
        # Keep caller-owned ORM instances coherent (tests and one-shot invocations reuse them).
        alert.last_scan_at = database_alert.last_scan_at

    for listing, label in notifications:
        await notifier(listing, label)
    duration = round(time.monotonic() - started, 3)
    print(json.dumps({
        "event": "scan", "alert": alert.id, "received": len(raw_items), "new": len(new_links),
        "enriched": enriched, "notified": len(notifications), "errors": errors, "duration_seconds": duration,
    }, ensure_ascii=False, sort_keys=True))
    return len(received_ids)


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
                await scan(alert, client)
            except Exception as error:
                async with SessionLocal() as db:
                    state = await db.get(WorkerState, 1) or WorkerState(id=1)
                    db.add(state)
                    state.last_error = f"{type(error).__name__}: {error}"
                    await db.commit()
                print(json.dumps({"event": "scan_error", "alert": alert.id, "error": str(error)}, ensure_ascii=False))
            await asyncio.sleep(max(1, 60 / settings.scan_global_rpm) + random.uniform(0, 2))
        await asyncio.sleep(20)


if __name__ == "__main__":
    asyncio.run(run())
