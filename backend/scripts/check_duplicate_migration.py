#!/usr/bin/env python3
import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def seed(connection) -> None:
    await connection.execute(text(
        """
        INSERT INTO alerts
          (id, name, include_terms, exclude_terms, filters, scan_minutes, notify_threshold, paused)
        VALUES
          (9001, 'Migration A', '[]'::json, '[]'::json, '{}'::json, 10, 'GOOD', false),
          (9002, 'Migration B', '[]'::json, '[]'::json, '{}'::json, 10, 'GOOD', false)
        """
    ))
    await connection.execute(text(
        """
        INSERT INTO listings
          (id, alert_id, external_id, title, description, price, shipping_estimate,
           buyer_fee, currency, url, image_urls, status, created_at, updated_at,
           score_sample_count)
        VALUES
          (9001, 9001, 'duplicate-vinted-id', 'Annonce A', '', 10, 0, 1, 'EUR',
           'https://www.vinted.fr/items/duplicate-vinted-id', '[]'::json,
           'ACTIVE'::listingstatus, now(), now(), 0),
          (9002, 9002, 'duplicate-vinted-id', 'Annonce B', '', 11, 0, 1, 'EUR',
           'https://www.vinted.fr/items/duplicate-vinted-id', '[]'::json,
           'ACTIVE'::listingstatus, now(), now(), 0)
        """
    ))
    print("seeded two legacy rows with one external id")


async def verify(connection) -> None:
    listing_count = await connection.scalar(text(
        "SELECT count(*) FROM listings WHERE external_id='duplicate-vinted-id'"
    ))
    link_count = await connection.scalar(text(
        """
        SELECT count(*) FROM alert_listings al
        JOIN listings l ON l.id=al.listing_id
        WHERE l.external_id='duplicate-vinted-id'
        """
    ))
    if (listing_count, link_count) != (1, 2):
        raise SystemExit(f"duplicate merge failed: listings={listing_count}, links={link_count}")
    print("duplicate migration verified: 1 global listing, 2 alert links")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "verify"))
    args = parser.parse_args()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await (seed(connection) if args.mode == "seed" else verify(connection))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
