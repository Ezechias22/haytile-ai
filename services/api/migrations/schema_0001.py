import sqlalchemy as sa

metadata = sa.MetaData()
sa.Table(
    "admin_audit",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
    sa.Column("actor_id", sa.String(length=36), primary_key=False, nullable=False),
    sa.Column("action", sa.String(length=80), primary_key=False, nullable=False),
    sa.Column("details", sa.JSON(), primary_key=False, nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
)
sa.Table(
    "models",
    metadata,
    sa.Column("studio", sa.String(length=20), primary_key=True, nullable=False),
    sa.Column("provider", sa.String(length=30), primary_key=False, nullable=False),
    sa.Column("model_id", sa.String(length=120), primary_key=False, nullable=False),
    sa.Column("enabled", sa.Boolean(), primary_key=False, nullable=False),
    sa.Column("credits", sa.Integer(), primary_key=False, nullable=False),
    sa.Column("terms_url", sa.Text(), primary_key=False, nullable=False),
    sa.Column("price_source", sa.Text(), primary_key=False, nullable=False),
    sa.Column(
        "verified_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
)
sa.Table(
    "rate_limits",
    metadata,
    sa.Column("key", sa.String(length=160), primary_key=True, nullable=False),
    sa.Column("count", sa.Integer(), primary_key=False, nullable=False),
    sa.Column(
        "reset_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
)
sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
    sa.Column("email", sa.String(length=254), primary_key=False, nullable=False),
    sa.Column("password", sa.Text(), primary_key=False, nullable=False),
    sa.Column("name", sa.String(length=80), primary_key=False, nullable=False),
    sa.Column("locale", sa.String(length=10), primary_key=False, nullable=False),
    sa.Column("role", sa.String(length=12), primary_key=False, nullable=False),
    sa.Column("balance", sa.Integer(), primary_key=False, nullable=False),
    sa.Column("reserved", sa.Integer(), primary_key=False, nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
    sa.UniqueConstraint("email"),
    sa.CheckConstraint("reserved >= 0"),
    sa.CheckConstraint("reserved <= balance"),
    sa.CheckConstraint("balance >= 0"),
)
sa.Table(
    "jobs",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
    sa.Column(
        "user_id",
        sa.String(length=36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=False,
        nullable=False,
    ),
    sa.Column("title", sa.String(length=120), primary_key=False, nullable=False),
    sa.Column("studio", sa.String(length=20), primary_key=False, nullable=False),
    sa.Column("prompt", sa.Text(), primary_key=False, nullable=False),
    sa.Column("params", sa.JSON(), primary_key=False, nullable=False),
    sa.Column(
        "idempotency_key", sa.String(length=80), primary_key=False, nullable=False
    ),
    sa.Column("status", sa.String(length=20), primary_key=False, nullable=False),
    sa.Column("progress", sa.Integer(), primary_key=False, nullable=False),
    sa.Column("error", sa.Text(), primary_key=False, nullable=True),
    sa.Column("credits", sa.Integer(), primary_key=False, nullable=False),
    sa.Column("attempt", sa.Integer(), primary_key=False, nullable=False),
    sa.Column(
        "lease_until", sa.DateTime(timezone=True), primary_key=False, nullable=True
    ),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
    sa.UniqueConstraint("user_id", "idempotency_key"),
)
sa.Index("ix_jobs_status", metadata.tables["jobs"].c["status"], unique=False)
sa.Index("ix_jobs_user_id", metadata.tables["jobs"].c["user_id"], unique=False)
sa.Table(
    "sessions",
    metadata,
    sa.Column("token_hash", sa.String(length=64), primary_key=True, nullable=False),
    sa.Column(
        "user_id",
        sa.String(length=36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=False,
        nullable=False,
    ),
    sa.Column(
        "expires_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
)
sa.Index("ix_sessions_user_id", metadata.tables["sessions"].c["user_id"], unique=False)
sa.Table(
    "assets",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
    sa.Column(
        "user_id",
        sa.String(length=36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=False,
        nullable=False,
    ),
    sa.Column(
        "job_id",
        sa.String(length=36),
        sa.ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=False,
        nullable=True,
    ),
    sa.Column("title", sa.String(length=120), primary_key=False, nullable=False),
    sa.Column("mime", sa.String(length=80), primary_key=False, nullable=False),
    sa.Column("key", sa.String(length=120), primary_key=False, nullable=False),
    sa.Column("size", sa.Integer(), primary_key=False, nullable=False),
    sa.Column("text", sa.Text(), primary_key=False, nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
    sa.UniqueConstraint("key"),
)
sa.Index("ix_assets_user_id", metadata.tables["assets"].c["user_id"], unique=False)
sa.Table(
    "credit_ledger",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
    sa.Column(
        "user_id",
        sa.String(length=36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=False,
        nullable=False,
    ),
    sa.Column(
        "job_id",
        sa.String(length=36),
        sa.ForeignKey("jobs.id", ondelete="SET NULL"),
        primary_key=False,
        nullable=True,
    ),
    sa.Column("amount", sa.Integer(), primary_key=False, nullable=False),
    sa.Column("kind", sa.String(length=30), primary_key=False, nullable=False),
    sa.Column("dedup_key", sa.String(length=160), primary_key=False, nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False
    ),
    sa.UniqueConstraint("dedup_key"),
)
sa.Index(
    "ix_credit_ledger_user_id",
    metadata.tables["credit_ledger"].c["user_id"],
    unique=False,
)
