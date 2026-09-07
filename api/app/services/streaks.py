"""Streaks and weekly volume (spec §7.6).

Both answer "how am I doing lately" without ever reducing to a number that can
be broken. §2.1 is explicit: never a zero-reset streak, always the rolling
window — "trained 4 of the last 14 days" survives a missed Tuesday in a way
that "0 day streak" does not.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.services.config import DEFAULT_WEEKLY_SET_TARGETS, STREAK_WINDOW_DAYS

__all__ = [
    "STREAK_WINDOW_DAYS",
    "Streaks",
    "VolumeRing",
    "count_streaks",
    "volume_rings",
    "week_start",
]


@dataclass(frozen=True)
class Streaks:
    logged_14: int
    trained_14: int


@dataclass(frozen=True)
class VolumeRing:
    muscle_group: str
    sets_this_week: int
    weekly_target: int


def week_start(day: date) -> date:
    """Monday of the week containing `day` (spec §7.6)."""
    return day - timedelta(days=day.weekday())


def count_streaks(
    *,
    logged_dates: set[date],
    trained_dates: set[date],
    as_of: date,
    window_days: int = STREAK_WINDOW_DAYS,
) -> Streaks:
    """Days in the trailing window with any entry, and with training.

    `trained_dates` should already combine `daily_logs.trained` with dates
    carrying a workout session — logging a session *is* evidence of training,
    whether or not the checkbox was also ticked.
    """
    window = {as_of - timedelta(days=i) for i in range(window_days)}
    return Streaks(
        logged_14=len(logged_dates & window),
        trained_14=len(trained_dates & window),
    )


def volume_rings(
    *,
    sets_by_group: dict[str, int],
    targets: dict[str, int] | None = None,
) -> list[VolumeRing]:
    """Sets performed this week per muscle group, against their targets.

    Every targeted group appears even at zero — a leg day that never happened is
    exactly what the user needs to see, and omitting empty groups would hide it.
    """
    targets = targets if targets is not None else DEFAULT_WEEKLY_SET_TARGETS

    groups = list(targets)
    groups += [group for group in sets_by_group if group not in targets]

    return [
        VolumeRing(
            muscle_group=group,
            sets_this_week=sets_by_group.get(group, 0),
            weekly_target=targets.get(group, 0),
        )
        for group in groups
    ]
