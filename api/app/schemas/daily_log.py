from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Splits offered by the workout tab (spec §2.3).
Split = Literal["push", "pull", "legs", "upper", "lower", "full", "other"]

# numeric(5,2) / numeric(6,2) in the schema — validate here so an out-of-range
# value returns a 422 naming the field rather than a 500 from the driver.
MAX_BODY_WEIGHT_KG = Decimal("999.99")

#: Typo guard, not a judgement about what anyone can walk: 200k steps is roughly
#: 150km, which no phone reports honestly (migration 0004).
MAX_STEPS = 200_000


class DailyLogUpsert(BaseModel):
    """Body of `PUT /daily-logs/{date}`.

    Every field is optional and *unset* is meaningful: only fields actually
    present in the request are written (spec §6). That is what lets the weight
    tab and the nutrition tab write to the same row without clobbering each
    other.
    """

    model_config = ConfigDict(extra="forbid")

    weight_kg: Decimal | None = Field(default=None, gt=0, le=MAX_BODY_WEIGHT_KG)
    calories: int | None = Field(default=None, ge=0, le=20_000)
    protein_g: int | None = Field(default=None, ge=0, le=10_000)
    carbs_g: int | None = Field(default=None, ge=0, le=10_000)
    fat_g: int | None = Field(default=None, ge=0, le=10_000)
    steps: int | None = Field(default=None, ge=0, le=MAX_STEPS)
    trained: bool | None = None
    split: Split | None = None


class DailyLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_date: date
    weight_kg: Decimal | None
    steps: int | None
    calories: int | None
    protein_g: int | None
    carbs_g: int | None
    fat_g: int | None
    trained: bool | None
    split: str | None
