"""Daily activity, for first-party analytics.

One row per user per day — not an event log. Everything else worth measuring is
already derivable from the tables in §5: signups from `profiles.created_at`,
feature use and retention from `daily_logs`, `workout_sessions` and `photos`.
The only fact missing is whether someone was present at all on a given day,
which is exactly what this records.

Deliberately narrow: no IP addresses, no user agents, no per-request rows, no
third-party SDK. It cannot answer "where was this person", only "were they
here", which is the question being asked.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_activity",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            # Cascades with everything else on account deletion (§5, §13).
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # The user's own local date, sent by the client — the server never
        # decides what day it is (§6).
        sa.Column("active_on", sa.Date(), primary_key=True),
    )
    # Retention and DAU both scan by date first.
    op.execute("create index ua_date on user_activity (active_on desc, user_id)")


def downgrade() -> None:
    op.drop_table("user_activity")
