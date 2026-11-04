"""Firestore metadata revision markers on disposable SQL projections."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("jobs", "assets", "projects"):
        op.add_column(table, sa.Column("remote_version", sa.String(80), nullable=True))


def downgrade():
    for table in ("projects", "assets", "jobs"):
        op.drop_column(table, "remote_version")
