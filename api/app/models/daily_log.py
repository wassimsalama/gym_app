import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyLog(Base):
    """One row per user per calendar day. Every measure column is independently
    nullable — a day may hold only weight, only macros, or only `trained`."""

    __tablename__ = "daily_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "log_date", name="daily_logs_user_id_log_date_key"),
        CheckConstraint("calories between 0 and 20000", name="daily_logs_calories_check"),
        CheckConstraint(
            "steps is null or (steps between 0 and 200000)", name="daily_logs_steps_check"
        ),
        Index("dl_user_date", "user_id", text("log_date DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    carbs_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fat_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: NULL is "not logged", which is a different fact from zero — see migration
    #: 0004. Aggregates must skip NULLs, never coalesce them to 0.
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trained: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    split: Mapped[str | None] = mapped_column(Text, nullable=True)
