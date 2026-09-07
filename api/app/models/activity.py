import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserActivity(Base):
    """One row per user per day they were present.

    Not an event log. Everything else worth measuring is derivable from the §5
    tables; this records only the fact that someone showed up, which nothing
    else can answer.
    """

    __tablename__ = "user_activity"
    __table_args__ = (Index("ua_date", text("active_on DESC"), "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    #: The user's own local date, supplied by the client (§6).
    active_on: Mapped[date] = mapped_column(Date, primary_key=True)
