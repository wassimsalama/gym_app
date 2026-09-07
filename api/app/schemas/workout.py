import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import MUSCLE_GROUPS
from app.schemas.daily_log import Split

MuscleGroup = Literal[MUSCLE_GROUPS]  # type: ignore[valid-type]

#: numeric(6,2) on set_logs.weight_kg.
MAX_SET_WEIGHT_KG = Decimal("9999.99")


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    muscle_group: str
    equipment: str | None
    source: str


class ExerciseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    # Constrained to the §5 vocabulary — a free-text group would break the
    # volume rings, which bucket by exactly these names (§7.6).
    muscle_group: MuscleGroup
    equipment: str | None = Field(default=None, max_length=60)


class SetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int
    set_number: int = Field(ge=1, le=100)
    weight_kg: Decimal = Field(ge=0, le=MAX_SET_WEIGHT_KG)
    reps: int = Field(ge=1, le=100)


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: int
    set_number: int
    weight_kg: Decimal
    reps: int


class LastSets(BaseModel):
    """What `GET /exercises/{id}/last-sets` returns — the prefill payload."""

    exercise_id: int
    session_date: date | None
    sets: list[SetOut]


class WorkoutSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Minted by the app so a retried POST cannot duplicate a session (§8).
    client_uuid: uuid.UUID
    session_date: date
    split: Split | None = None
    notes: str | None = Field(default=None, max_length=2000)
    sets: list[SetIn] = Field(default_factory=list, max_length=200)


class WorkoutSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_uuid: uuid.UUID
    session_date: date
    split: str | None
    notes: str | None
    sets: list[SetOut]


class PersonalRecordOut(BaseModel):
    exercise_id: int
    exercise_name: str
    e1rm: float
    previous_e1rm: float


class WorkoutSessionSaved(BaseModel):
    """201 body for a session save (spec §6)."""

    session: WorkoutSessionOut
    prs: list[PersonalRecordOut]
