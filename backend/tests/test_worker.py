from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Alert, Base, Listing, ListingProductMatch, PriceStat, Product
from app.worker import scan


def item(identifier: int, price: float, buyer_fee: float = 0, shipping: float = 0) -> dict:
    return {
        "id": identifier,
        "title": "LEGO Technic 42146",
        "description": "Boîte complète",
        "price": {"amount": str(price), "currency_code": "EUR"},
        "service_fee_amount": {"amount": str(buyer_fee)},
        "shipping_price": {"amount": str(shipping)},
        "url": f"https://www.vinted.fr/items/{identifier}",
        "photo": {"url": f"https://images.example/{identifier}.jpg"},
        "photos": [
            {"url": f"https://images.example/{identifier}.jpg"},
            {"url": f"https://images.example/{identifier}-2.jpg"},
        ],
        "user": {"login": "vendeur_test", "feedback_reputation": 4.9, "feedback_count": 27},
        "status": "Très bon état",
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

    baseline = [item(1, 20), item(2, 30), item(3, 40), item(4, 50)]
    assert await scan(alert, FakeClient(baseline), session_factory=sessions, notifier=notifier) == 4
    assert sent == []

    second_scan = baseline + [item(5, 5, buyer_fee=1.5, shipping=2.5)]
    assert await scan(alert, FakeClient(second_scan), session_factory=sessions, notifier=notifier) == 5
    assert sent == [("5", "DEAL")]

    async with sessions() as db:
        listing = await db.scalar(select(Listing).where(Listing.external_id == "5"))
        count = await db.scalar(select(func.count()).select_from(Listing))
        match_count = await db.scalar(select(func.count()).select_from(ListingProductMatch))
        product = await db.scalar(select(Product).where(Product.canonical_key == "lego:42146"))
        statistic = await db.scalar(select(PriceStat).where(PriceStat.product_id == product.id))
        stored_alert = await db.get(Alert, alert.id)
        assert count == 5
        assert match_count == 5
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
        FakeClient([item(1, 10), item(2, 20), item(3, 30), item(4, 40), item(5, 35)]),
        session_factory=sessions,
        notifier=notifier,
    )
    assert sent
    assert all(label == "DEAL" for _, label in sent)
    assert "5" not in {external_id for external_id, _ in sent}
    await engine.dispose()
