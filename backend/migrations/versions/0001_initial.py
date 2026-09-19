"""Initial VintRadar schema, frozen independently from current ORM models."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


listing_status = postgresql.ENUM(
    "ACTIVE",
    "SOLD_CONFIRMED",
    "DISAPPEARED",
    "DELETED",
    "UNKNOWN",
    name="listingstatus",
    create_type=False,
)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        listing_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("include_terms", sa.JSON(), nullable=False),
        sa.Column("exclude_terms", sa.JSON(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("min_price", sa.Float(), nullable=True),
        sa.Column("max_price", sa.Float(), nullable=True),
        sa.Column("scan_minutes", sa.Integer(), nullable=False),
        sa.Column("notify_threshold", sa.String(length=20), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_key", sa.String(length=300), nullable=False, unique=True),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.String(length=5000), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("shipping_estimate", sa.Float(), nullable=False),
        sa.Column("buyer_fee", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("condition", sa.String(length=80), nullable=True),
        sa.Column("size", sa.String(length=80), nullable=True),
        sa.Column("status", listing_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("alert_id", "external_id"),
    )
    op.create_index("ix_listings_alert_id", "listings", ["alert_id"])
    op.create_index("ix_listings_external_id", "listings", ["external_id"])
    op.create_table(
        "listing_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("status", listing_status, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_listing_snapshots_listing_id", "listing_snapshots", ["listing_id"])
    op.create_table(
        "listing_product_match",
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_table(
        "price_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("condition", sa.String(length=80), nullable=False),
        sa.Column("median", sa.Float(), nullable=False),
        sa.Column("p20", sa.Float(), nullable=False),
        sa.Column("p75", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
    )
    op.create_index("ix_price_stats_product_id", "price_stats", ["product_id"])
    op.create_table(
        "external_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_external_prices_product_id", "external_prices", ["product_id"])
    op.create_table(
        "user_flags",
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("seen", sa.Boolean(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_flags")
    op.drop_index("ix_external_prices_product_id", table_name="external_prices")
    op.drop_table("external_prices")
    op.drop_index("ix_price_stats_product_id", table_name="price_stats")
    op.drop_table("price_stats")
    op.drop_table("listing_product_match")
    op.drop_index("ix_listing_snapshots_listing_id", table_name="listing_snapshots")
    op.drop_table("listing_snapshots")
    op.drop_index("ix_listings_external_id", table_name="listings")
    op.drop_index("ix_listings_alert_id", table_name="listings")
    op.drop_table("listings")
    op.drop_table("products")
    op.drop_table("alerts")
    if op.get_bind().dialect.name == "postgresql":
        listing_status.drop(op.get_bind(), checkfirst=True)
