from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Alert, AlertListing, Base, Listing, ListingProductMatch, PriceStat, Product
from app.worker import scan
from app.vinted import ItemDetail, VintedError


def item(identifier: int, price: float, buyer_fee: float = 0, shipping: float = 0) -> dict:
    return {
        "id": identifier,
        "title": "LEGO Technic 42146",
        "description": "Boîte complète",
        "price": {"amount": str(price), "currency_code": "EUR"},
        "service_fee_amount": {"amount": str(buyer_fee)},
        "shipping_price": {"amount": str(shipping)},
        "url": f"/items/{identifier}-lego-technic-42146",
        "photo": {"url": f"https://images.example/{identifier}.jpg"},
        "photos": [
            {"url": f"https://images.example/{identifier}.jpg"},
            {"url": f"https://images.example/{identifier}-2.jpg"},
        ],
        "user": {"login": "vendeur_test", "feedback_reputation": 4.9, "feedback_count": 27},
        "item_box": {"second_line": "Taille unique · Très bon état"},
    }


class FakeClient:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    async def search(self, alert) -> list[dict]:
        return self.items


@pytest.mark.asyncio
async def test_first_scan_seeds_without_notifications_then_scores_new_items(tmp_path) -> None:
    database = tmp_path / "worker.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        alert = Alert(
            name="LEGO",
            include_terms=["lego"],
            exclude_terms=[],
            notify_threshold="DEAL",
            scan_minutes=5,
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)

    sent: list[tuple[str, str]] = []

    async def notifier(listing, label):
        sent.append((listing.external_id, label))

    baseline = [item(1, 20), item(2, 30), item(3, 40), item(4, 50), item(5, 60)]
    assert await scan(alert, FakeClient(baseline), session_factory=sessions, notifier=notifier) == 5
    assert sent == []

    second_scan = baseline + [item(6, 5, buyer_fee=1.5, shipping=2.5)]
    assert await scan(alert, FakeClient(second_scan), session_factory=sessions, notifier=notifier) == 6
    assert sent == [("6", "DEAL")]

    async with sessions() as db:
        listing = await db.scalar(select(Listing).where(Listing.external_id == "6"))
        count = await db.scalar(select(func.count()).select_from(Listing))
        match_count = await db.scalar(select(func.count()).select_from(ListingProductMatch))
        product = await db.scalar(select(Product).where(Product.canonical_key == "lego:42146"))
        statistic = await db.scalar(select(PriceStat).where(PriceStat.product_id == product.id))
        stored_alert = await db.get(Alert, alert.id)
        assert count == 6
        assert match_count == 6
        assert listing is not None
        assert listing.score_label == "DEAL"
        assert listing.score_percentile == 0
        assert listing.score_sample_count >= 3
        assert listing.buyer_fee == 1.5
        assert listing.shipping_estimate == 2.5
        assert len(listing.image_urls) == 2
        assert listing.seller_name == "vendeur_test"
        assert listing.seller_rating == 4.9
        assert listing.seller_reviews_count == 27
        assert listing.url == "https://www.vinted.fr/items/6"
        assert listing.size == "Taille unique"
        assert listing.condition == "Très bon état"
        assert statistic.sample_count == 5
        assert stored_alert.last_scan_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_threshold_blocks_non_deal_notification(tmp_path) -> None:
    database = tmp_path / "threshold.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        alert = Alert(
            name="LEGO",
            include_terms=["lego"],
            exclude_terms=[],
            notify_threshold="DEAL",
            scan_minutes=5,
            last_scan_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)

    sent: list[tuple[str, str]] = []

    async def notifier(listing, label):
        sent.append((listing.external_id, label))

    await scan(
        alert,
        FakeClient([item(1, 10), item(2, 20), item(3, 30), item(4, 40), item(5, 50), item(6, 35)]),
        session_factory=sessions,
        notifier=notifier,
    )
    assert sent
    assert all(label == "DEAL" for _, label in sent)
    assert "6" not in {external_id for external_id, _ in sent}
    await engine.dispose()


class EnrichingClient:
    def __init__(self, items, details):
        self.items = items
        self.details = details
        self.request_history = []

    async def search(self, alert, **kwargs):
        if kwargs.get("search_text"):
            return []
        return self.items

    async def detail(self, external_id):
        value = self.details[external_id]
        if isinstance(value, Exception):
            raise value
        return value


def detail(identifier: str, status: str = "ACTIVE") -> ItemDetail:
    return ItemDetail(
        identifier, f"LEGO 42146 enrichi {identifier}", "Description enrichie réf LEGO 42146",
        [f"https://images.example/{identifier}.jpg"], "LEGO", "Unique", "Très bon état",
        "1767", "Jeux de construction", ["Enfants", "Jeux de construction"], ["Bleu"],
        None, 12, 84, 4.5, status,
        {"id": "seller", "name": "vendeur", "rating": 4.9, "reviews_count": 20},
        f"https://www.vinted.fr/items/{identifier}",
    )


@pytest.mark.asyncio
async def test_enrichment_precedes_rescore_and_notification(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'enrichment.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        alert = Alert(
            name="LEGO", include_terms=["lego"], exclude_terms=[],
            notify_threshold="ALL", scan_minutes=2, last_scan_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
    values = [item(index, 20 + index) for index in range(1, 7)]
    client = EnrichingClient(values, {str(index): detail(str(index)) for index in range(1, 7)})
    observed = []

    async def notifier(listing, label):
        observed.append((listing.description, listing.pricing_explanation["product"]["key"], label))

    await scan(alert, client, session_factory=sessions, notifier=notifier)
    assert len(observed) == 6
    assert all(value[0].startswith("Description enrichie") for value in observed)
    assert all(value[1] == "lego:42146" for value in observed)
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_items_have_three_verified_outcomes(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'statuses.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        alert = Alert(name="LEGO", include_terms=["lego"], exclude_terms=[], scan_minutes=2, last_scan_at=datetime.now(timezone.utc))
        db.add(alert)
        await db.flush()
        for identifier in ("sold", "deleted", "unknown"):
            listing = Listing(
                external_id=identifier, title=f"LEGO {identifier}", price=10, total_item_price=11,
                url=f"https://www.vinted.fr/items/{identifier}", status="ACTIVE",
            )
            db.add(listing)
            await db.flush()
            db.add(AlertListing(alert_id=alert.id, listing_id=listing.id))
        await db.commit()
        await db.refresh(alert)
    client = EnrichingClient([], {
        "sold": detail("sold", "SOLD_CONFIRMED"),
        "deleted": detail("deleted", "DELETED"),
        "unknown": VintedError("unusable response"),
    })
    await scan(alert, client, session_factory=sessions, notifier=lambda *_: None)
    async with sessions() as db:
        statuses = {value.external_id: value.status.value for value in await db.scalars(select(Listing))}
    assert statuses == {"sold": "SOLD_CONFIRMED", "deleted": "DELETED", "unknown": "DISAPPEARED"}
    await engine.dispose()
