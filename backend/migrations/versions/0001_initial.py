"""initial schema"""
from alembic import op
revision="0001";down_revision=None;branch_labels=None;depends_on=None
def upgrade():
    from app.models import Base
    Base.metadata.create_all(op.get_bind())
def downgrade():
    from app.models import Base
    Base.metadata.drop_all(op.get_bind())
