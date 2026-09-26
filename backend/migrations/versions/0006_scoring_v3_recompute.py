"""Invalidate v0.2 scores after enrichment and comparable fixes.

Revision ID: 0006
Revises: 0005
"""

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.execute("UPDATE products SET targeted_at = NULL")


def downgrade() -> None:
    # Data invalidation is intentionally not reversible.
    pass
