"""Daily step count.

NULL means "not logged", which is not the same fact as zero. A day someone
forgot to sync their phone must never read as a day they did not move, because
every average and every observation built on top would be dragged down by it —
and this column feeds the suggestions engine, which tells people things about
their own health. The column is therefore nullable with no default, and every
aggregate over it must skip NULLs rather than coalesce them.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A brisk day is ~20k. The ceiling is a typo guard, not a judgement about what
#: anyone can walk — 200k is roughly 150km, which no phone reports honestly.
MAX_STEPS = 200_000


def upgrade() -> None:
    op.add_column("daily_logs", sa.Column("steps", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "daily_logs_steps_check",
        "daily_logs",
        f"steps is null or (steps between 0 and {MAX_STEPS})",
    )


def downgrade() -> None:
    op.drop_constraint("daily_logs_steps_check", "daily_logs", type_="check")
    op.drop_column("daily_logs", "steps")
