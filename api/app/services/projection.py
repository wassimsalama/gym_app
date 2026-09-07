"""Goal progress and projection.

The spec fixes the *shape* of this (§6 `goal`, §2.4 "projected goal date from
current trend") but not the formula, so the approach mirrors §7.2's TDEE
estimate: ordinary least squares over the smoothed series. Using smoothed
values matters — regressing raw weights lets one bad morning swing the
projected date by weeks.

Spec §2.6 is explicit that status comes from the trend, not from wishful maths:
a projection is refused outright rather than flattered when the trend does not
actually point at the goal.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.services.smoothing import WeightPoint
from app.services.stats import least_squares_slope

#: Trailing window the trend is fitted over. Matches §7.2's TDEE window so the
#: two numbers on the dashboard can never disagree about which way weight moved.
TREND_WINDOW_DAYS = 21

#: Below this daily rate the trend is indistinguishable from noise, and dividing
#: by it produces absurd dates (0.001 kg/day turns 5 kg into 13 years).
MIN_MEANINGFUL_SLOPE_KG_PER_DAY = 0.005

#: A projection further out than this is not information the user can act on.
MAX_PROJECTION_DAYS = 730

#: Within this margin the goal counts as reached.
GOAL_TOLERANCE_KG = 0.05


@dataclass(frozen=True)
class GoalProgress:
    progress_pct: float
    projected_date: date | None
    on_track: bool | None


def progress_pct(start_kg: float, goal_kg: float, current_kg: float) -> float:
    """How far along the journey, 0–100, clamped at both ends.

    Clamping is deliberate: overshooting a goal is still 100% of it, and moving
    the wrong way is 0%, not a negative number the progress bar cannot draw.
    """
    total = goal_kg - start_kg
    if abs(total) < GOAL_TOLERANCE_KG:
        # Start and goal coincide — nothing to travel, so it is already met.
        return 100.0

    travelled = current_kg - start_kg
    return max(0.0, min(100.0, travelled / total * 100.0))


def trend_slope_kg_per_day(
    points: list[WeightPoint], *, as_of: date, window_days: int = TREND_WINDOW_DAYS
) -> float | None:
    """Least-squares slope of the smoothed series over the trailing window."""
    cutoff = as_of - timedelta(days=window_days - 1)
    window = [p for p in points if cutoff <= p.date <= as_of]
    if len(window) < 2:
        return None

    origin = window[0].date
    xs = [float((p.date - origin).days) for p in window]
    ys = [p.smoothed_kg for p in window]
    return least_squares_slope(xs, ys)


def project_goal_date(
    current_kg: float, goal_kg: float, slope_kg_per_day: float | None, *, as_of: date
) -> date | None:
    """When the current trend reaches the goal, or None if it never will.

    Returns None rather than a flattering guess when the trend is flat, points
    away from the goal, or lands beyond `MAX_PROJECTION_DAYS`.
    """
    remaining = goal_kg - current_kg
    if abs(remaining) <= GOAL_TOLERANCE_KG:
        return as_of

    if slope_kg_per_day is None or abs(slope_kg_per_day) < MIN_MEANINGFUL_SLOPE_KG_PER_DAY:
        return None

    # Moving away from the goal, or the wrong side of it.
    if (remaining > 0) != (slope_kg_per_day > 0):
        return None

    days_out = remaining / slope_kg_per_day
    if days_out > MAX_PROJECTION_DAYS:
        return None
    return as_of + timedelta(days=round(days_out))


def evaluate(
    *,
    start_kg: float,
    goal_kg: float,
    points: list[WeightPoint],
    as_of: date,
    target_date: date | None = None,
) -> GoalProgress:
    """Everything the dashboard's `goal` block needs (spec §6)."""
    current = points[-1].smoothed_kg if points else start_kg

    slope = trend_slope_kg_per_day(points, as_of=as_of)
    projected = project_goal_date(current, goal_kg, slope, as_of=as_of)

    # Without both a target and a projection there is nothing honest to compare.
    on_track = None if target_date is None or projected is None else projected <= target_date

    return GoalProgress(
        progress_pct=progress_pct(start_kg, goal_kg, current),
        projected_date=projected,
        on_track=on_track,
    )
