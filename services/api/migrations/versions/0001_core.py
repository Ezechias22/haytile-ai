"""Initial core schema. Frozen model metadata for repeatable migration."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Initial DDL is frozen in schema_0001; future application models cannot alter this migration.
    from migrations.schema_0001 import metadata

    metadata.create_all(bind=op.get_bind())


def downgrade():
    from migrations.schema_0001 import metadata

    metadata.drop_all(bind=op.get_bind())
