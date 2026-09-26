#!/usr/bin/env python3
import asyncio

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


EXPECTED_TABLES = {
    "alerts",
    "alert_listings",
    "external_prices",
    "listing_product_match",
    "listing_snapshots",
    "listings",
    "price_stats",
    "products",
    "seller_profiles",
    "user_flags",
    "worker_state",
}


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        dialect = await connection.run_sync(lambda sync_connection: sync_connection.dialect.name)
        tables = set(await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names()))
        columns = {
            column["name"]
            for column in await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns("listings")
            )
        }
    await engine.dispose()
    missing = EXPECTED_TABLES - tables
    if missing:
        raise SystemExit(f"Missing PostgreSQL tables after migration: {sorted(missing)}")
    expected_listing_columns = {
        "score_label",
        "score_percentile",
        "score_median",
        "score_sample_count",
        "score_confidence",
        "image_urls",
        "seller_name",
        "seller_rating",
        "seller_reviews_count",
        "total_item_price",
        "category_id",
        "condition_segment",
        "pricing_explanation",
        "enrichment_error",
        "scoring_version",
        "first_seen_at",
    }
    missing_columns = expected_listing_columns - columns
    if missing_columns:
        raise SystemExit(f"Missing listings columns after migration: {sorted(missing_columns)}")
    print(f"{dialect} migration verified: {len(EXPECTED_TABLES)} tables, required listing columns present")


if __name__ == "__main__":
    asyncio.run(main())
