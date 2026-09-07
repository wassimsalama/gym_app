"""Weekly recap (spec §7.7).

Covers the most recent *completed* Monday–Sunday week. A recap of a week still
in progress is a half-finished thought, and §2.1 wants this screenshot-friendly
— self-contained enough that sending it to a training partner needs no
explanation.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class BestLift:
    exercise_id: int
    exercise_name: str
    e1rm: float
    previous_best: float | None

    @property
    def was_a_record(self) -> bool:
        return self.previous_best is not None and self.e1rm > self.previous_best


@dataclass(frozen=True)
class Recap:
    week_start: date
    week_end: date
    sessions: int
    total_sets: int
    #: Σ weight × reps across every set — tonnage moved.
    total_volume_kg: float
    weight_delta_kg: float | None
    days_trained: int
    days_logged: int
    best_lift: BestLift | None


def last_completed_week(as_of: date) -> tuple[date, date]:
    """Monday and Sunday of the last week that has finished.

    Called on a Sunday, this returns the week *before* — that Sunday is not over
    yet, and a recap that changes as the day goes on is not a recap.
    """
    this_monday = as_of - timedelta(days=as_of.weekday())
    last_monday = this_monday - timedelta(days=7)
    return last_monday, last_monday + timedelta(days=6)


def build(
    *,
    as_of: date,
    session_dates: list[date],
    set_volumes: list[tuple[float, int]],
    logged_dates: set[date],
    trained_dates: set[date],
    smoothed_start: float | None,
    smoothed_end: float | None,
    best_lift: BestLift | None,
) -> Recap:
    """Assemble the week's numbers.

    Everything is passed in already scoped to the week; this module does the
    arithmetic and none of the querying, which keeps it testable without a
    database.
    """
    week_start, week_end = last_completed_week(as_of)
    in_week = {week_start + timedelta(days=i) for i in range(7)}

    delta = (
        smoothed_end - smoothed_start
        if smoothed_start is not None and smoothed_end is not None
        else None
    )

    return Recap(
        week_start=week_start,
        week_end=week_end,
        sessions=len([d for d in session_dates if d in in_week]),
        total_sets=len(set_volumes),
        total_volume_kg=sum(weight * reps for weight, reps in set_volumes),
        weight_delta_kg=delta,
        days_trained=len(trained_dates & in_week),
        days_logged=len(logged_dates & in_week),
        best_lift=best_lift,
    )
