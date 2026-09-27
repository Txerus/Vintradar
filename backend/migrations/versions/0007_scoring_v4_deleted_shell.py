"""Recompute scores after detecting Vinted's HTTP-200 deleted shell.

Revision ID: 0007
Revises: 0006
"""

from alembic import op


revision = "0007"
down_revision = "0006"
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
        WHERE status::text IN ('ACTIVE', 'RESERVED')
        """
    )


def downgrade() -> None:
    pass
