#!/usr/bin/env python3
import argparse
import asyncio
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Listing


async def main() -> None:
    parser = argparse.ArgumentParser(description="Print a stored VintRadar pricing explanation.")
    parser.add_argument("id", type=int, help="Internal VintRadar listing id")
    args = parser.parse_args()
    async with SessionLocal() as database:
        listing = await database.scalar(select(Listing).where(Listing.id == args.id))
        if listing is None:
            raise SystemExit(f"Listing {args.id} not found")
        print(f"{listing.title} — {listing.total_item_price:.2f} {listing.currency}")
        print(json.dumps(listing.pricing_explanation, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
