"""Cardio sessions.

Mirrors workout_sessions deliberately: same `client_uuid` idempotency key, same
user scoping, same date-only granularity. The offline queue (§8) replays writes
whose responses were lost, and a duplicated session would overstate activity
just as a duplicated lift would corrupt volume.

Separate from workout_sessions rather than a `kind` column on it. A workout is
sets of an exercise; a cardio session is a duration and an optional distance.
Merging them would make almost every column nullable and every query filter on
a discriminator, to save one table.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typo guards, not limits on what anyone can do: 24h and 1000km.
MAX_DURATION_MIN = 1440
MAX_DISTANCE_KM = 1000


def upgrade() -> None:
    op.create_table(
        "cardio_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("activity", sa.Text(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        # Nullable: a rowing machine reports distance, a class does not. Absent
        # is "not measured", never zero.
        sa.Column("distance_km", sa.Numeric(6, 2), nullable=True),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"duration_min between 1 and {MAX_DURATION_MIN}",
            name="cardio_sessions_duration_check",
        ),
        sa.CheckConstraint(
            f"distance_km is null or (distance_km >= 0 and distance_km <= {MAX_DISTANCE_KM})",
            name="cardio_sessions_distance_check",
        ),
    )
    op.create_index("cs_user_date", "cardio_sessions", ["user_id", sa.text("session_date DESC")])

    # Row level security, same as every other table (migration 0003): the API
    # holds the service key, and the published anon key must reach nothing.
    op.execute("alter table cardio_sessions enable row level security")


def downgrade() -> None:
    op.drop_index("cs_user_date", table_name="cardio_sessions")
    op.drop_table("cardio_sessions")
