import uuid

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Kept in sync with the muscle_group comment in the §5 schema.
MUSCLE_GROUPS = (
    "chest",
    "back",
    "shoulders",
    "biceps",
    "triceps",
    "quads",
    "hamstrings",
    "glutes",
    "calves",
    "core",
    "other",
)


class Exercise(Base):
    """Seeded catalogue (source='seed') plus user-created ones (source='custom')."""

    __tablename__ = "exercises"
    __table_args__ = (
        Index(
            "ex_search",
            text("to_tsvector('simple', name)"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    muscle_group: Mapped[str] = mapped_column(Text, nullable=False)
    equipment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="seed")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=True
    )
