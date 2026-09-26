"""Invalidate legacy scores and persist enrichment failures.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("enrichment_error", sa.Text(), nullable=True))
    op.add_column(
        "listings",
        sa.Column("scoring_version", sa.Integer(), nullable=False, server_default="0"),
    )
    # A legacy badge must disappear immediately, before the post-migration rescore runs.
    op.execute(
        """
        UPDATE listings
        SET score_label = NULL,
            score_percentile = NULL,
            score_median = NULL,
            score_sample_count = 0,
            score_confidence = NULL,
            pricing_explanation = '{}',
            scoring_version = 0
        """
    )
    op.alter_column("listings", "scoring_version", server_default=None)


def downgrade() -> None:
    op.drop_column("listings", "scoring_version")
    op.drop_column("listings", "enrichment_error")
