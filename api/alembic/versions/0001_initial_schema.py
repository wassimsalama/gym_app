"""Initial schema (spec §5).

Canonical unit is kg everywhere in the database and API; display conversion
happens only in the app's lib/units.ts.

Revision ID: 0001
Revises:
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.Text()),
        sa.Column("unit", sa.Text(), nullable=False, server_default="lb"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("unit in ('kg','lb')", name="profiles_unit_check"),
    )

    op.create_table(
        "goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_weight_kg", sa.Numeric(5, 2), nullable=False),
        sa.Column("goal_weight_kg", sa.Numeric(5, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("target_date", sa.Date()),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('active','achieved','abandoned')", name="goals_status_check"
        ),
    )

    op.create_table(
        "daily_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2)),
        sa.Column("calories", sa.Integer()),
        sa.Column("protein_g", sa.Integer()),
        sa.Column("carbs_g", sa.Integer()),
        sa.Column("fat_g", sa.Integer()),
        sa.Column("trained", sa.Boolean()),
        sa.Column("split", sa.Text()),
        sa.CheckConstraint("calories between 0 and 20000", name="daily_logs_calories_check"),
        sa.UniqueConstraint("user_id", "log_date", name="daily_logs_user_id_log_date_key"),
    )
    op.execute("create index dl_user_date on daily_logs (user_id, log_date desc)")

    op.create_table(
        "exercises",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        # chest|back|shoulders|biceps|triceps|quads|hamstrings|glutes|calves|core|other
        sa.Column("muscle_group", sa.Text(), nullable=False),
        sa.Column("equipment", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False, server_default="seed"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id"),
        ),
    )
    op.execute("create index ex_search on exercises using gin (to_tsvector('simple', name))")

    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        # Idempotency key minted by the app.
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("split", sa.Text()),
        sa.Column("notes", sa.Text()),
    )
    op.execute("create index ws_user_date on workout_sessions (user_id, session_date desc)")

    op.create_table(
        "set_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("workout_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exercise_id", sa.BigInteger(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column("set_number", sa.SmallInteger(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("reps", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("reps between 1 and 100", name="set_logs_reps_check"),
    )
    op.create_index("sl_exercise", "set_logs", ["exercise_id"])

    op.create_table(
        "photos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("thumb_key", sa.Text()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("create index ph_user_date on photos (user_id, taken_on desc)")


def downgrade() -> None:
    op.drop_table("photos")
    op.drop_table("set_logs")
    op.drop_table("workout_sessions")
    op.drop_table("exercises")
    op.drop_table("daily_logs")
    op.drop_table("goals")
    op.drop_table("profiles")
