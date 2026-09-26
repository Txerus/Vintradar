"""Re-enrich and recompute active listings with the current pricing engine."""

import argparse
import asyncio
import json
from collections import Counter
from types import SimpleNamespace

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Listing, ListingProductMatch, ListingStatus, Product
from app.price_sources import RebrickableValidator
from app.vinted import VintedClient
from app.worker import (
    SCORING_VERSION,
    _apply_detail,
    _match_product,
    _normalization,
    _score_and_explain,
    _targeted_collect,
)


def _metrics(listings: list[Listing]) -> dict:
    active = [value for value in listings if value.status == ListingStatus.ACTIVE]
    failures = [value for value in active if value.enrichment_error]
    unevaluated = [value for value in active if not (value.pricing_explanation or {}).get("evaluated")]
    reasons = Counter(
        (value.pricing_explanation or {}).get("reason") or "(sans raison)"
        for value in unevaluated
    )
    total = len(active)
    return {
        "active": total,
        "enrichment_failures": len(failures),
        "enrichment_failure_rate": round(len(failures) / total, 4) if total else 0,
        "unevaluated": len(unevaluated),
        "unevaluated_rate": round(len(unevaluated) / total, 4) if total else 0,
        "unevaluated_reasons": dict(sorted(reasons.items())),
    }


async def rescore(*, pending_only: bool = False, targeted: bool = True, client=None) -> dict:
    vinted = client or VintedClient()
    validator = RebrickableValidator()
    result = {
        "selected": 0, "enriched": 0, "enrichment_errors": 0,
        "targeted_products": 0, "targeted_collected": 0,
        "evaluated": 0, "unevaluated": 0,
    }
    async with SessionLocal() as db:
        original_active = list(await db.scalars(
            select(Listing).where(Listing.status == ListingStatus.ACTIVE).order_by(Listing.id)
        ))
        original_ids = [value.id for value in original_active]
        result["before"] = _metrics(original_active)
        statement = select(Listing).where(Listing.status == ListingStatus.ACTIVE).order_by(Listing.id)
        if pending_only:
            statement = statement.where(Listing.scoring_version < SCORING_VERSION)
        listings = list(await db.scalars(statement))
        result["selected"] = len(listings)

        # Normalize the whole corpus first: no listing is scored against stale v0.1 matches.
        for listing in listings:
            try:
                detail = await vinted.detail(listing.external_id)
                _apply_detail(listing, detail)
                result["enriched"] += 1
            except Exception as error:
                listing.enrichment_error = f"{type(error).__name__}: {error}"
                result["enrichment_errors"] += 1
            normalized = await _normalization(listing, validator)
            await _match_product(db, listing, normalized)
        await db.flush()

        for listing in listings:
            await _score_and_explain(db, listing)
        await db.flush()

        if targeted:
            matches = list(await db.scalars(select(ListingProductMatch).where(
                ListingProductMatch.listing_id.in_([
                    value.id for value in listings
                    if (value.pricing_explanation or {}).get("reason")
                    == "moins de 5 annonces comparables admissibles sur 90 jours"
                ])
            )))
            product_ids = list(dict.fromkeys(
                value.product_id for value in matches if value.product_id
            ))[:settings.targeted_search_daily_budget]
            products = list(await db.scalars(select(Product).where(Product.id.in_(product_ids)))) if product_ids else []
            result["targeted_products"] = len(products)
            if products:
                search_context = SimpleNamespace(
                    include_terms=[], exclude_terms=[], min_price=None, max_price=None, filters={},
                )
                result["targeted_collected"] = await _targeted_collect(
                    db, vinted, search_context, products, validator, force=True,
                )
                await db.flush()

        result["evaluated"] = result["unevaluated"] = 0
        for listing in listings:
            score = await _score_and_explain(db, listing)
            result["evaluated" if score else "unevaluated"] += 1
        await db.commit()
        after = list(await db.scalars(select(Listing).where(Listing.id.in_(original_ids)))) if original_ids else []
        result["after"] = _metrics(after)
    print(json.dumps({"event": "rescore_all", **result}, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Only process listings invalidated by a scoring migration.",
    )
    parser.add_argument(
        "--no-targeted",
        action="store_true",
        help="Skip targeted Vinted searches for products lacking comparables.",
    )
    args = parser.parse_args()
    asyncio.run(rescore(pending_only=args.pending, targeted=not args.no_targeted))


if __name__ == "__main__":
    main()
