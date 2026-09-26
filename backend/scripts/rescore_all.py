"""Re-enrich and recompute active listings with the current pricing engine."""

import argparse
import asyncio
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Listing, ListingStatus
from app.price_sources import RebrickableValidator
from app.vinted import VintedClient
from app.worker import (
    SCORING_VERSION,
    _apply_detail,
    _match_product,
    _normalization,
    _score_and_explain,
)


async def rescore(*, pending_only: bool = False, client=None) -> dict[str, int]:
    vinted = client or VintedClient()
    validator = RebrickableValidator()
    result = {"selected": 0, "enriched": 0, "enrichment_errors": 0, "evaluated": 0, "unevaluated": 0}
    async with SessionLocal() as db:
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
            score = await _score_and_explain(db, listing)
            result["evaluated" if score else "unevaluated"] += 1
        await db.commit()
    print(json.dumps({"event": "rescore_all", **result}, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Only process listings invalidated by a scoring migration.",
    )
    args = parser.parse_args()
    asyncio.run(rescore(pending_only=args.pending))


if __name__ == "__main__":
    main()
