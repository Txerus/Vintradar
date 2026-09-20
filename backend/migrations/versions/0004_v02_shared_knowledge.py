"""VintRadar v0.2 shared listings, enrichment and explainable pricing."""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE listingstatus ADD VALUE IF NOT EXISTS 'RESERVED'")

    op.add_column("alerts", sa.Column("bootstrap_pages_done", sa.Integer(), server_default="0", nullable=False))
    op.create_table(
        "alert_listings",
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Link every legacy row to its alert before merging duplicate external ids.
    op.execute(
        """
        INSERT INTO alert_listings (alert_id, listing_id, first_detected_at)
        SELECT l.alert_id, keep.id, l.created_at
        FROM listings l
        JOIN (
          SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id
        ) keep ON keep.external_id = l.external_id
        ON CONFLICT (alert_id, listing_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE listing_snapshots s SET listing_id = keep.id
        FROM listings old
        JOIN (SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id) keep
          ON keep.external_id = old.external_id
        WHERE s.listing_id = old.id AND old.id <> keep.id
        """
    )
    op.execute(
        """
        INSERT INTO user_flags (listing_id, favorite, seen, hidden)
        SELECT keep.id, bool_or(f.favorite), bool_or(f.seen), bool_or(f.hidden)
        FROM user_flags f
        JOIN listings old ON old.id = f.listing_id
        JOIN (SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id) keep
          ON keep.external_id = old.external_id
        GROUP BY keep.id
        ON CONFLICT (listing_id) DO UPDATE SET
          favorite = EXCLUDED.favorite, seen = EXCLUDED.seen, hidden = EXCLUDED.hidden
        """
    )
    op.execute(
        """
        INSERT INTO listing_product_match (listing_id, product_id, confidence)
        SELECT DISTINCT ON (keep.id) keep.id, m.product_id, m.confidence
        FROM listing_product_match m
        JOIN listings old ON old.id = m.listing_id
        JOIN (SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id) keep
          ON keep.external_id = old.external_id
        ORDER BY keep.id, m.confidence DESC
        ON CONFLICT (listing_id) DO UPDATE SET
          product_id = EXCLUDED.product_id,
          confidence = GREATEST(listing_product_match.confidence, EXCLUDED.confidence)
        """
    )
    op.execute(
        """
        DELETE FROM listing_product_match m USING listings old,
          (SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id) keep
        WHERE m.listing_id = old.id AND keep.external_id = old.external_id AND old.id <> keep.id
        """
    )
    op.execute(
        """
        DELETE FROM user_flags f USING listings old,
          (SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id) keep
        WHERE f.listing_id = old.id AND keep.external_id = old.external_id AND old.id <> keep.id
        """
    )
    op.execute(
        """
        DELETE FROM listings old USING
          (SELECT external_id, MIN(id) AS id FROM listings GROUP BY external_id) keep
        WHERE keep.external_id = old.external_id AND old.id <> keep.id
        """
    )
    op.drop_constraint("listings_alert_id_external_id_key", "listings", type_="unique")
    op.drop_constraint("listings_alert_id_fkey", "listings", type_="foreignkey")
    op.drop_index("ix_listings_alert_id", table_name="listings")
    op.drop_column("listings", "alert_id")
    op.drop_index("ix_listings_external_id", table_name="listings")
    op.create_index("ix_listings_external_id", "listings", ["external_id"], unique=True)
    op.alter_column("listings", "description", type_=sa.Text(), existing_type=sa.String(5000))

    listing_columns = [
        sa.Column("total_item_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("brand", sa.String(160), nullable=True),
        sa.Column("category_id", sa.String(80), nullable=True),
        sa.Column("category_name", sa.String(200), nullable=True),
        sa.Column("category_path", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("colors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("seller_id", sa.String(80), nullable=True),
        sa.Column("seller_location", sa.String(240), nullable=True),
        sa.Column("seller_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seller_last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("condition_segment", sa.String(40), nullable=True),
        sa.Column("favourite_count", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_price", sa.Float(), nullable=True),
        sa.Column("pricing_explanation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]
    for column in listing_columns:
        op.add_column("listings", column)
    op.execute("UPDATE listings SET total_item_price = price + buyer_fee")
    op.execute("UPDATE listings SET first_seen_at = created_at")
    op.drop_column("listings", "created_at")
    op.create_index("ix_listings_category_id", "listings", ["category_id"])
    op.create_index("ix_listings_seller_id", "listings", ["seller_id"])
    op.create_index("ix_listings_condition_segment", "listings", ["condition_segment"])
    op.create_index("ix_listings_first_seen_at", "listings", ["first_seen_at"])

    op.add_column("listing_snapshots", sa.Column("total_item_price", sa.Float(), nullable=False, server_default="0"))
    op.add_column("listing_snapshots", sa.Column("favourite_count", sa.Integer(), nullable=True))
    op.add_column("listing_snapshots", sa.Column("view_count", sa.Integer(), nullable=True))
    op.execute("UPDATE listing_snapshots SET total_item_price = price")

    op.add_column("products", sa.Column("category_key", sa.String(160), nullable=True))
    op.add_column("products", sa.Column("targeted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_products_category_key", "products", ["category_key"])
    op.alter_column("listing_product_match", "product_id", nullable=True)
    op.add_column("listing_product_match", sa.Column("recognized_text", sa.String(500), nullable=True))
    op.add_column("listing_product_match", sa.Column("excluded_from_stats", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("listing_product_match", sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.alter_column("price_stats", "window_days", server_default=None)
    op.add_column("price_stats", sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_unique_constraint("uq_price_stats_product_condition", "price_stats", ["product_id", "condition"])
    op.add_column("external_prices", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.execute(
        """
        DELETE FROM external_prices old USING external_prices keep
        WHERE old.product_id = keep.product_id AND old.source = keep.source AND old.id > keep.id
        """
    )
    op.create_unique_constraint("uq_external_prices_product_source", "external_prices", ["product_id", "source"])

    op.create_table(
        "seller_profiles",
        sa.Column("seller_id", sa.String(80), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "worker_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("recent_403_count", sa.Integer(), nullable=False),
        sa.Column("recent_429_count", sa.Integer(), nullable=False),
        sa.Column("enrichment_queue_size", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("0004 merges duplicate listings and is intentionally irreversible")
