from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import session
from app.main import app
from app.models import Base, Listing, ListingSnapshot, ListingStatus


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
            alert_id=alert_id,
            external_id="v-1",
            title="Console rétro",
            price=50,
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
            status=ListingStatus.ACTIVE,
        )
        database.add(listing)
        await database.flush()
        database.add(
            ListingSnapshot(
                listing_id=listing.id,
                price=50,
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
    assert response.json()[0]["image_urls"] == ["https://images.example/1.jpg"]
    assert response.json()[0]["seller_name"] == "vendeur_test"
    history = await client.get(f"/listings/{listing_id}/history", headers=auth_headers())
    assert len(history.json()) == 1
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
