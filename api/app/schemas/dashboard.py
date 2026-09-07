"""Response shape for `GET /dashboard` (spec §6).

The home tab makes exactly one request, so this mirrors §6's structure in full
from day one — including the blocks Phases 2–3 will fill in. They return empty
collections and nulls rather than being absent, so the app is written once
against the final shape and never reshaped as phases land.
"""

from datetime import date

from pydantic import BaseModel


class Streaks(BaseModel):
    logged_14: int
    trained_14: int


class WeightSeriesPoint(BaseModel):
    date: date
    raw_kg: float
    smoothed_kg: float


class WeightBlock(BaseModel):
    current_smoothed_kg: float | None
    delta_since_start_kg: float | None
    series: list[WeightSeriesPoint]


class GoalBlock(BaseModel):
    progress_pct: float
    projected_date: date | None
    on_track: bool | None
    # The two numbers the percentage is derived from. Without them a 0% bar is
    # unreadable, and §6 gives the home tab exactly one request to work with —
    # so they travel here rather than forcing a second call to /goals/active.
    start_weight_kg: float
    goal_weight_kg: float


class TdeeBlock(BaseModel):
    estimate_kcal: int | None
    days_of_data: int
    reliable: bool


class VolumeRing(BaseModel):
    muscle_group: str
    sets_this_week: int
    weekly_target: int


class Suggestion(BaseModel):
    id: str
    kind: str
    message: str
    evidence: dict


class Dashboard(BaseModel):
    streaks: Streaks
    weight: WeightBlock
    # Null only before onboarding has set one; §2.6 makes a goal part of first
    # launch, so in practice the app always has one by the time it gets here.
    goal: GoalBlock | None
    tdee: TdeeBlock
    volume: list[VolumeRing]
    prs_recent: list[dict]
    suggestions: list[Suggestion]
    recap: dict | None
