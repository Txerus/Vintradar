import importlib
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Listing, ListingStatus
from app.vinted import ItemDetail, VintedError


def switch_detail(identifier: str) -> ItemDetail:
    return ItemDetail(
        external_id=identifier,
        title="Nintendo Switch 2 neuve",
        description="Console Nintendo Switch 2 complète",
        photos=[f"https://images.example/{identifier}.jpg"],
        brand="Nintendo",
        size=None,
        condition="Neuf avec étiquette",
        category_id="console",
        category_name="Consoles",
        category_path=["Jeux vidéo", "Consoles"],
        colors=["Noir"],
        published_at=None,
        favourite_count=2,
        view_count=20,
        shipping=None,
        status="ACTIVE",
        seller={"id": f"seller-{identifier}"},
        source_url=f"https://www.vinted.fr/items/{identifier}",
    )


class DetailClient:
    async def detail(self, external_id: str):
        if external_id == "failure":
            raise VintedError("detail unavailable")
        return switch_detail(external_id)


def test_compose_runs_pending_rescore_after_migrations() -> None:
    compose = (Path(__file__).parents[2] / "docker-compose.yml").read_text()
    command = 'alembic upgrade head && python scripts/rescore_all.py --pending'
    assert command in compose


@pytest.mark.asyncio
async def test_rescore_all_reenriches_active_legacy_rows_and_clears_stale_badges(tmp_path, monkeypatch) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rescore.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        for index in range(6):
            db.add(Listing(
                external_id=str(index), title="Switch 2", description="", price=400 + index,
                total_item_price=410 + index, url=f"https://www.vinted.fr/items/{index}",
                score_label="DEAL", pricing_explanation={}, scoring_version=0,
                status=ListingStatus.ACTIVE,
            ))
        db.add(Listing(
            external_id="failure", title="Objet inconnu", description="", price=8,
            total_item_price=9, url="https://www.vinted.fr/items/failure",
            score_label="DEAL", pricing_explanation={}, scoring_version=0,
            status=ListingStatus.ACTIVE,
        ))
        await db.commit()

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("rescore_all")
    monkeypatch.setattr(module, "SessionLocal", sessions)
    result = await module.rescore(client=DetailClient())
    assert result == {
        "selected": 7, "enriched": 6, "enrichment_errors": 1,
        "evaluated": 6, "unevaluated": 1,
    }
    async with sessions() as db:
        rows = list(await db.scalars(select(Listing).order_by(Listing.id)))
        assert all(row.scoring_version == 2 for row in rows)
        assert all(row.pricing_explanation for row in rows)
        assert all(row.score_label is not None for row in rows[:6])
        assert rows[-1].score_label is None
        assert "detail unavailable" in rows[-1].enrichment_error
    await engine.dispose()
