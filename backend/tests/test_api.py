from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import session
from app.main import app
from app.models import AlertListing, Base, Listing, ListingProductMatch, ListingSnapshot, ListingStatus, Product
from app.vinted import ItemDetail


@pytest.fixture
async def api_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with sessions() as database:
            yield database

    app.dependency_overrides[session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, sessions
    app.dependency_overrides.clear()
    await engine.dispose()


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.vintradar_api_token}"}


@pytest.mark.asyncio
async def test_authentication_and_alert_crud(api_client) -> None:
    client, _ = api_client
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/auth/check")).status_code == 401
    assert (await client.get("/auth/check", headers=auth_headers())).status_code == 200

    invalid = await client.post(
        "/alerts",
        headers=auth_headers(),
        json={"name": "Invalid", "min_price": 100, "max_price": 10},
    )
    assert invalid.status_code == 422

    created = await client.post(
        "/alerts",
        headers=auth_headers(),
        json={
            "name": "LEGO",
            "include_terms": ["lego"],
            "exclude_terms": ["lot"],
            "filters": {"catalog": "123"},
            "min_price": 10,
            "max_price": 100,
            "scan_minutes": 5,
            "notify_threshold": "GOOD",
            "paused": False,
        },
    )
    assert created.status_code == 200
    alert_id = created.json()["id"]
    paused = await client.post(f"/alerts/{alert_id}/pause", headers=auth_headers())
    assert paused.json()["paused"] is True
    alerts = await client.get("/alerts", headers=auth_headers())
    assert [alert["name"] for alert in alerts.json()] == ["LEGO"]
    assert (await client.delete(f"/alerts/{alert_id}", headers=auth_headers())).status_code == 204


@pytest.mark.asyncio
async def test_alert_preview_and_all_threshold(api_client, monkeypatch) -> None:
    import importlib
    main_module = importlib.import_module("app.main")

    class PreviewClient:
        async def search(self, alert):
            assert alert.include_terms == ["switch 2"]
            return [{"id": index} for index in range(7)]

    monkeypatch.setattr(main_module, "VintedClient", PreviewClient)
    client, _ = api_client
    response = await client.post(
        "/alerts/preview",
        headers=auth_headers(),
        json={
            "name": "Switch", "include_terms": ["switch 2"], "scan_minutes": 2,
            "notify_threshold": "ALL",
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 7
    assert response.json()["sampled"] == 7


@pytest.mark.asyncio
async def test_listings_history_flags_and_dashboard(api_client) -> None:
    client, sessions = api_client
    created = await client.post(
        "/alerts",
        headers=auth_headers(),
        json={"name": "Console", "include_terms": ["console"]},
    )
    alert_id = created.json()["id"]
    async with sessions() as database:
        listing = Listing(
            external_id="v-1",
            title="Console rétro",
            price=50,
            total_item_price=55,
            url="https://www.vinted.fr/items/1",
            image_urls=["https://images.example/1.jpg"],
            seller_name="vendeur_test",
            seller_rating=4.8,
            seller_reviews_count=12,
            score_label="GOOD",
            score_percentile=0.3,
            score_median=70,
            score_sample_count=10,
            score_confidence="MEDIUM",
            pricing_explanation={
                "evaluated": True,
                "price": {"item": 50, "buyer_fee": 5, "shipping": 0, "total": 55},
                "product": {"key": "console:switch2:console", "confidence": 1, "text": "Console"},
                "condition_segment": "GOOD",
                "window_days": 90,
                "count": 10,
                "median": 70,
                "p20": 50,
                "p75": 80,
                "percentile": .3,
                "confidence": "MEDIUM",
                "comparable_ids": [],
            },
            status=ListingStatus.ACTIVE,
        )
        database.add(listing)
        await database.flush()
        database.add(AlertListing(alert_id=alert_id, listing_id=listing.id))
        product = Product(canonical_key="console:switch2:console", model="Switch 2")
        database.add(product)
        await database.flush()
        database.add(ListingProductMatch(
            listing_id=listing.id, product_id=product.id, confidence=1,
            recognized_text="Console Switch 2",
        ))
        database.add(
            ListingSnapshot(
                listing_id=listing.id,
                price=50,
                total_item_price=55,
                status=ListingStatus.ACTIVE,
                observed_at=datetime.now(timezone.utc),
            )
        )
        await database.commit()
        await database.refresh(listing)
        listing_id = listing.id

    response = await client.get("/listings", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()[0]["score_label"] == "GOOD"
    assert response.json()[0]["alert_ids"] == [alert_id]
    assert response.json()[0]["total_item_price"] == 55
    assert response.json()[0]["image_urls"] == ["https://images.example/1.jpg"]
    assert response.json()[0]["seller_name"] == "vendeur_test"
    history = await client.get(f"/listings/{listing_id}/history", headers=auth_headers())
    assert len(history.json()) == 1
    pricing = await client.get(f"/listings/{listing_id}/pricing", headers=auth_headers())
    assert pricing.status_code == 200
    assert pricing.json()["explanation"]["median"] == 70
    assert pricing.json()["comparables"] == []
    favorite = await client.put(
        f"/listings/{listing_id}/favorite",
        headers=auth_headers(),
        json={"value": True},
    )
    assert favorite.status_code == 200
    flags = await client.get("/flags", headers=auth_headers())
    assert flags.json()[0]["favorite"] is True
    missing = await client.put(
        "/listings/999/favorite",
        headers=auth_headers(),
        json={"value": True},
    )
    assert missing.status_code == 404
    dashboard = await client.get("/dashboard", headers=auth_headers())
    assert dashboard.json()["alerts"] == 1
    assert dashboard.json()["listings"] == 1
    assert dashboard.json()["active"] == 1
    worker = await client.get("/worker/status", headers=auth_headers())
    assert worker.status_code == 200
    assert worker.json()["enrichment_queue_size"] == 0
    assert worker.json()["recent_403_count"] == 0

    correction = await client.put(
        f"/listings/{listing_id}/product",
        headers=auth_headers(),
        json={"canonical_key": "console:switch2:oled-pack", "exclude_from_stats": False},
    )
    assert correction.status_code == 200
    async with sessions() as database:
        match = await database.get(ListingProductMatch, listing_id)
        assert match.manual is True
        assert (await database.get(Product, match.product_id)).canonical_key == "console:switch2:oled-pack"


@pytest.mark.asyncio
async def test_empty_explanation_suppresses_badge_and_returns_unevaluated_payload(api_client) -> None:
    client, sessions = api_client
    async with sessions() as database:
        listing = Listing(
            external_id="legacy", title="Switch 2", description="", price=420,
            total_item_price=430, url="https://www.vinted.fr/items/legacy",
            score_label="DEAL", score_median=8, score_sample_count=29,
            pricing_explanation={"evaluated": False}, status=ListingStatus.ACTIVE,
        )
        database.add(listing)
        await database.commit()
        await database.refresh(listing)
        identifier = listing.id
    payload = (await client.get("/listings", headers=auth_headers())).json()[0]
    assert payload["pricing_evaluated"] is False
    assert payload["score_label"] is None
    assert payload["pricing_explanation"]["reason"]
    pricing = (await client.get(f"/listings/{identifier}/pricing", headers=auth_headers())).json()
    assert pricing["explanation"]["evaluated"] is False
    assert "recalcul" in pricing["explanation"]["reason"]


@pytest.mark.asyncio
async def test_manual_enrichment_endpoint_persists_details_and_recalculates(api_client, monkeypatch) -> None:
    import importlib
    main_module = importlib.import_module("app.main")

    class Client:
        async def detail(self, external_id):
            return ItemDetail(
                external_id=external_id, title="Volant Nacon Switch 2",
                description="Volant compatible Nintendo Switch 2", photos=[], brand="Nacon",
                size=None, condition="Très bon état", category_id="accessory",
                category_name="Accessoires jeux vidéo", category_path=["Jeux vidéo", "Accessoires"],
                colors=["Noir"], published_at=None, favourite_count=3, view_count=21,
                shipping=None, status="ACTIVE", seller={},
                source_url=f"https://www.vinted.fr/items/{external_id}",
            )

    monkeypatch.setattr(main_module, "VintedClient", Client)
    client, sessions = api_client
    async with sessions() as database:
        listing = Listing(
            external_id="wheel", title="Volant", description="", price=8,
            total_item_price=9, url="https://www.vinted.fr/items/wheel",
            status=ListingStatus.ACTIVE,
        )
        database.add(listing)
        await database.commit()
        await database.refresh(listing)
        identifier = listing.id
    response = await client.post(f"/listings/{identifier}/enrich", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["description"].startswith("Volant compatible")
    assert response.json()["category_name"] == "Accessoires jeux vidéo"
    assert response.json()["colors"] == ["Noir"]
    assert response.json()["enrichment_error"] is None
    async with sessions() as database:
        match = await database.get(ListingProductMatch, identifier)
        product = await database.get(Product, match.product_id)
        assert product.canonical_key == "accessory:switch2:steering-wheel"
