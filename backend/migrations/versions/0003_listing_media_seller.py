"""Persist listing galleries and public seller summary fields."""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column("image_urls", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("listings", sa.Column("seller_name", sa.String(length=160), nullable=True))
    op.add_column("listings", sa.Column("seller_rating", sa.Float(), nullable=True))
    op.add_column("listings", sa.Column("seller_reviews_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "seller_reviews_count")
    op.drop_column("listings", "seller_rating")
    op.drop_column("listings", "seller_name")
    op.drop_column("listings", "image_urls")
