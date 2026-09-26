#!/usr/bin/env python3
"""Replay failed Vinted enrichments and print redacted request diagnostics."""

import argparse
import asyncio
import dataclasses
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Listing, ListingStatus
from app.price_sources import RebrickableValidator
from app.vinted import VintedClient
from app.worker import _apply_detail, _match_product, _normalization, _score_and_explain


async def run(limit: int, apply: bool) -> None:
    client = VintedClient()
    validator = RebrickableValidator()
    async with SessionLocal() as db:
        listings = list(await db.scalars(
            select(Listing).where(
                Listing.status == ListingStatus.ACTIVE,
                Listing.enrichment_error.is_not(None),
            ).order_by(Listing.id).limit(limit)
        ))
        print(json.dumps({"event": "diagnose_enrichment_start", "selected": len(listings), "apply": apply}))
        for listing in listings:
            client.request_history = []
            error = None
            detail = None
            try:
                detail = await client.detail(listing.external_id)
                if apply:
                    _apply_detail(listing, detail)
                    await _match_product(db, listing, await _normalization(listing, validator))
                    await db.flush()
                    await _score_and_explain(db, listing)
            except Exception as caught:
                error = f"{type(caught).__name__}: {caught}"
                if apply:
                    listing.enrichment_error = error
            print(json.dumps({
                "listing_id": listing.id,
                "external_id": listing.external_id,
                "result": dataclasses.asdict(detail) if detail else None,
                "error": error,
                "requests": [dataclasses.asdict(value) for value in client.request_history],
            }, ensure_ascii=False, sort_keys=True))
        if apply:
            await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--apply", action="store_true", help="Persist successful enrichments and rescores.")
    args = parser.parse_args()
    asyncio.run(run(max(1, args.limit), args.apply))


if __name__ == "__main__":
    main()
