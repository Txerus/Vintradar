"""Store server-side robust scores on listings."""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("score_label", sa.String(length=20), nullable=True))
    op.add_column("listings", sa.Column("score_percentile", sa.Float(), nullable=True))
    op.add_column("listings", sa.Column("score_median", sa.Float(), nullable=True))
    op.add_column(
        "listings",
        sa.Column("score_sample_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("listings", sa.Column("score_confidence", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "score_confidence")
    op.drop_column("listings", "score_sample_count")
    op.drop_column("listings", "score_median")
    op.drop_column("listings", "score_percentile")
    op.drop_column("listings", "score_label")
