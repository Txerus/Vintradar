from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import session
from app.models import (
    Alert, AlertListing, Listing, ListingProductMatch, ListingSnapshot, Product, UserFlag, WorkerState,
)
from app.schemas import (
    AlertIn, AlertOut, AlertPreviewOut, DashboardOut, FlagIn, FlagOut, ListingOut,
    PricingOut, ProductCorrectionIn, SnapshotOut,
)
from app.security import require_token
from app.vinted import VintedClient, VintedError
from app.worker import enrich_and_rescore


app = FastAPI(title="VintRadar API", version="0.2.0")


def _complete_pricing_explanation(value: Listing) -> dict:
    payload = dict(value.pricing_explanation or {})
    if payload.get("evaluated") is not True:
        payload["evaluated"] = False
        payload["reason"] = payload.get("reason") or value.enrichment_error or "recalcul du prix en attente"
    payload.setdefault("price", {
        "item": value.price,
        "buyer_fee": value.buyer_fee,
        "shipping": value.shipping_estimate,
        "total": value.total_item_price,
    })
    payload.setdefault("product", {"key": None, "model": None, "confidence": 0, "text": None})
    payload.setdefault("condition_segment", value.condition_segment)
    payload.setdefault("window_days", 90)
    payload.setdefault("external_references", [])
    return payload


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/auth/check", dependencies=[Depends(require_token)])
async def auth_check():
    return {"status": "ok"}


@app.get("/alerts", response_model=list[AlertOut], dependencies=[Depends(require_token)])
async def alerts(db: AsyncSession = Depends(session)):
    return (await db.scalars(select(Alert).order_by(Alert.id))).all()


@app.post("/alerts", response_model=AlertOut, dependencies=[Depends(require_token)])
async def create_alert(body: AlertIn, db: AsyncSession = Depends(session)):
    alert = Alert(**body.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@app.post("/alerts/preview", response_model=AlertPreviewOut, dependencies=[Depends(require_token)])
async def preview_alert(body: AlertIn, db: AsyncSession = Depends(session)):
    client = VintedClient()
    try:
        items = await client.search(SimpleNamespace(**body.model_dump()))
    except VintedError as error:
        raise HTTPException(502, str(error)) from error
    existing = list(await db.scalars(select(Alert).where(Alert.paused.is_(False))))
    requests_per_day = sum(1440 / max(2, value.scan_minutes) for value in existing) + 1440 / body.scan_minutes
    warning = None
    if requests_per_day > settings.scan_daily_budget:
        warning = "La fréquence cumulée dépasse le budget prudent configuré."
    return AlertPreviewOut(count=len(items), sampled=len(items), budget_warning=warning)


@app.get("/alerts/{aid}", response_model=AlertOut, dependencies=[Depends(require_token)])
async def get_alert(aid: int, db: AsyncSession = Depends(session)):
    alert = await db.get(Alert, aid)
    if not alert:
        raise HTTPException(404)
    return alert


@app.patch("/alerts/{aid}", response_model=AlertOut, dependencies=[Depends(require_token)])
async def patch_alert(aid: int, body: AlertIn, db: AsyncSession = Depends(session)):
    alert = await db.get(Alert, aid)
    if not alert:
        raise HTTPException(404)
    for key, value in body.model_dump().items():
        setattr(alert, key, value)
    await db.commit()
    await db.refresh(alert)
    return alert


@app.delete("/alerts/{aid}", status_code=204, dependencies=[Depends(require_token)])
async def delete_alert(aid: int, db: AsyncSession = Depends(session)):
    alert = await db.get(Alert, aid)
    if not alert:
        raise HTTPException(404)
    await db.delete(alert)
    await db.commit()


@app.post("/alerts/{aid}/pause", response_model=AlertOut, dependencies=[Depends(require_token)])
async def pause(aid: int, db: AsyncSession = Depends(session)):
    alert = await db.get(Alert, aid)
    if not alert:
        raise HTTPException(404)
    alert.paused = not alert.paused
    await db.commit()
    await db.refresh(alert)
    return alert


async def _listing_payloads(db: AsyncSession, values: list[Listing]) -> list[dict]:
    if not values:
        return []
    rows = (await db.execute(
        select(AlertListing.listing_id, AlertListing.alert_id).where(
            AlertListing.listing_id.in_([value.id for value in values])
        )
    )).all()
    links: dict[int, list[int]] = {}
    for listing_id, alert_id in rows:
        links.setdefault(listing_id, []).append(alert_id)
    output = []
    for value in values:
        payload = {column.name: getattr(value, column.name) for column in Listing.__table__.columns}
        payload["pricing_explanation"] = _complete_pricing_explanation(value)
        evaluated = bool(payload["pricing_explanation"].get("evaluated"))
        payload["pricing_evaluated"] = evaluated
        if not evaluated:
            payload["score_label"] = None
            payload["score_percentile"] = None
            payload["score_median"] = None
            payload["score_sample_count"] = 0
            payload["score_confidence"] = None
        payload["alert_ids"] = sorted(links.get(value.id, []))
        payload["alert_id"] = payload["alert_ids"][0] if payload["alert_ids"] else None
        output.append(payload)
    return output


@app.get("/listings", response_model=list[ListingOut], dependencies=[Depends(require_token)])
async def listings(
    alert_id: int | None = None, q: str | None = None,
    limit: int = Query(50, le=100), offset: int = 0,
    db: AsyncSession = Depends(session),
):
    statement = select(Listing).order_by(Listing.first_seen_at.desc()).limit(limit).offset(offset)
    if alert_id:
        statement = statement.join(AlertListing).where(AlertListing.alert_id == alert_id)
    if q:
        statement = statement.where(Listing.title.ilike(f"%{q}%"))
    values = list(await db.scalars(statement))
    return await _listing_payloads(db, values)


@app.get("/listings/{lid}", response_model=ListingOut, dependencies=[Depends(require_token)])
async def listing(lid: int, db: AsyncSession = Depends(session)):
    value = await db.get(Listing, lid)
    if not value:
        raise HTTPException(404)
    return (await _listing_payloads(db, [value]))[0]


@app.get("/listings/{lid}/history", response_model=list[SnapshotOut], dependencies=[Depends(require_token)])
async def listing_history(lid: int, db: AsyncSession = Depends(session)):
    return (await db.scalars(
        select(ListingSnapshot).where(ListingSnapshot.listing_id == lid).order_by(ListingSnapshot.observed_at)
    )).all()


@app.get("/listings/{lid}/pricing", response_model=PricingOut, dependencies=[Depends(require_token)])
async def listing_pricing(lid: int, db: AsyncSession = Depends(session)):
    value = await db.get(Listing, lid)
    if not value:
        raise HTTPException(404)
    explanation = _complete_pricing_explanation(value)
    identifiers = [int(identifier) for identifier in explanation.get("comparable_ids", [])]
    comparables = list(await db.scalars(select(Listing).where(Listing.id.in_(identifiers)))) if identifiers else []
    return {
        "listing_id": value.id,
        "explanation": explanation,
        "comparables": [{
            "id": item.id, "title": item.title, "total_item_price": item.total_item_price,
            "condition": item.condition, "image_url": item.image_url, "status": item.status,
            "first_seen_at": item.first_seen_at, "url": item.url,
        } for item in comparables],
    }


@app.post("/listings/{lid}/enrich", response_model=ListingOut, dependencies=[Depends(require_token)])
async def enrich_listing_endpoint(lid: int, db: AsyncSession = Depends(session)):
    value = await db.get(Listing, lid)
    if not value:
        raise HTTPException(404, "Annonce introuvable")
    await enrich_and_rescore(db, value, VintedClient())
    await db.commit()
    await db.refresh(value)
    return (await _listing_payloads(db, [value]))[0]


@app.put("/listings/{lid}/product", dependencies=[Depends(require_token)])
async def correct_product(lid: int, body: ProductCorrectionIn, db: AsyncSession = Depends(session)):
    value = await db.get(Listing, lid)
    if not value:
        raise HTTPException(404)
    match = await db.get(ListingProductMatch, lid)
    if match is None:
        match = ListingProductMatch(listing_id=lid)
        db.add(match)
    product = None
    if body.canonical_key:
        product = await db.scalar(select(Product).where(Product.canonical_key == body.canonical_key))
        if product is None:
            product = Product(canonical_key=body.canonical_key, model=body.canonical_key.rsplit(":", 1)[-1])
            db.add(product)
            await db.flush()
    match.product_id = product.id if product else match.product_id
    match.manual = True
    match.excluded_from_stats = body.exclude_from_stats
    match.confidence = 1 if product else match.confidence
    match.recognized_text = "Correction manuelle" if product else match.recognized_text
    await db.commit()
    return {"ok": True, "canonical_key": product.canonical_key if product else None, "excluded": match.excluded_from_stats}


@app.get("/flags", response_model=list[FlagOut], dependencies=[Depends(require_token)])
async def flags(db: AsyncSession = Depends(session)):
    return (await db.scalars(select(UserFlag).order_by(UserFlag.listing_id))).all()


async def set_flag(lid: int, key: str, body: FlagIn, db: AsyncSession):
    if not await db.get(Listing, lid):
        raise HTTPException(404, "Annonce introuvable")
    flag = await db.get(UserFlag, lid)
    if not flag:
        flag = UserFlag(listing_id=lid)
        db.add(flag)
    setattr(flag, key, body.value)
    await db.commit()
    return {"ok": True}


@app.put("/listings/{lid}/favorite", dependencies=[Depends(require_token)])
async def favorite(lid: int, body: FlagIn, db: AsyncSession = Depends(session)):
    return await set_flag(lid, "favorite", body, db)


@app.put("/listings/{lid}/seen", dependencies=[Depends(require_token)])
async def seen(lid: int, body: FlagIn, db: AsyncSession = Depends(session)):
    return await set_flag(lid, "seen", body, db)


@app.put("/listings/{lid}/hidden", dependencies=[Depends(require_token)])
async def hidden(lid: int, body: FlagIn, db: AsyncSession = Depends(session)):
    return await set_flag(lid, "hidden", body, db)


@app.get("/dashboard", response_model=DashboardOut, dependencies=[Depends(require_token)])
async def dashboard(db: AsyncSession = Depends(session)):
    alerts_count = await db.scalar(select(func.count()).select_from(Alert))
    listings_count = await db.scalar(select(func.count()).select_from(Listing))
    active = await db.scalar(select(func.count()).select_from(Listing).where(Listing.status == "ACTIVE"))
    last = await db.scalar(select(func.max(Alert.last_scan_at)))
    return DashboardOut(alerts=alerts_count or 0, listings=listings_count or 0, active=active or 0, last_scan_at=last)


@app.get("/worker/status", dependencies=[Depends(require_token)])
async def worker_status(db: AsyncSession = Depends(session)):
    state = await db.get(WorkerState, 1)
    return {
        "last_scan_at": state.last_scan_at if state else None,
        "last_error": state.last_error if state else None,
        "recent_403_count": state.recent_403_count if state else 0,
        "recent_429_count": state.recent_429_count if state else 0,
        "enrichment_queue_size": state.enrichment_queue_size if state else 0,
        "now": datetime.now(timezone.utc),
    }
