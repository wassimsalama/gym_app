from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.daily_log import MAX_BODY_WEIGHT_KG


class GoalCreate(BaseModel):
    """Body of `POST /goals` (spec §6).

    `start_weight_kg` and `start_date` are deliberately absent: the spec says
    start weight is taken automatically from the log (§2.6), so the server reads
    the user's most recent weight rather than trusting a client-supplied number.
    Taking the *date* from that same observation also avoids the server ever
    deciding what "today" is, which §6 forbids.
    """

    model_config = ConfigDict(extra="forbid")

    goal_weight_kg: Decimal = Field(gt=0, le=MAX_BODY_WEIGHT_KG)
    target_date: date | None = None


class GoalUpdate(BaseModel):
    """Body of `PATCH /goals/active`.

    `start_weight_kg` is editable, which is a deliberate deviation from §7.1 —
    see DECISIONS.md. The spec fixes the baseline so that adjusting a target
    cannot silently reset progress to zero, and that reasoning still holds for
    *targets*. It does not hold for a mistyped starting weight: the only route
    to fixing one was starting a new goal, which threw away the goal's history
    to correct a number that was never right.

    `start_date` remains untouched. Moving it would change which observations
    count toward the trend, which is re-baselining, and re-baselining is
    `POST /goals` — an explicit new goal.

    Unset fields are left alone; `target_date: null` clears the date.
    """

    model_config = ConfigDict(extra="forbid")

    goal_weight_kg: Decimal | None = Field(default=None, gt=0, le=MAX_BODY_WEIGHT_KG)
    start_weight_kg: Decimal | None = Field(default=None, gt=0, le=MAX_BODY_WEIGHT_KG)
    target_date: date | None = None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_weight_kg: Decimal
    goal_weight_kg: Decimal
    start_date: date
    target_date: date | None
    status: str
