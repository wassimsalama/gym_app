"""Product metrics, computed from the app's own data (spec §1, revised).

The original spec forbade analytics SDKs. That still holds — nothing here
phones anywhere, sets a cookie, or records an IP address. These are queries
over tables the app already fills for its own purposes, plus one narrow record
of which days a user showed up.

The arithmetic lives here as pure functions so the definitions are visible and
testable. "Retention" means whatever the code says it means, and vague metrics
are worse than none.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Cohort:
    """Users who signed up in one week, and how many came back."""

    week_start: date
    signed_up: int
    returned_week_1: int
    #: False while the cohort's return window is still running.
    complete: bool = True

    @property
    def retention_pct(self) -> float | None:
        """None until the window has actually elapsed.

        A cohort that joined four days ago has not had a week to come back in.
        Reporting that as 0% is a number worn with more confidence than it has
        earned, and it makes a healthy launch look like a failing one.
        """
        if not self.complete or self.signed_up == 0:
            return None
        return self.returned_week_1 / self.signed_up * 100


def active_in_window(activity: dict[date, set], *, as_of: date, days: int) -> int:
    """Distinct users present in the trailing window, inclusive of `as_of`."""
    window = {as_of - timedelta(days=i) for i in range(days)}
    present: set = set()
    for day, users in activity.items():
        if day in window:
            present |= users
    return len(present)


def retention(
    signups: dict[date, set],
    activity: dict[date, set],
    *,
    week_start: date,
    as_of: date | None = None,
) -> Cohort:
    """Of the users who joined in a week, how many were back the week after.

    Week-1 retention rather than day-1: a training app is used a few times a
    week, so a day-1 measure mostly records whether someone happened to train
    the following morning.
    """
    following_start = week_start + timedelta(days=7)
    window_ends = following_start + timedelta(days=14)
    complete = as_of is None or as_of >= window_ends

    joined: set = set()
    for day, users in signups.items():
        if week_start <= day < week_start + timedelta(days=7):
            joined |= users

    if not joined:
        return Cohort(week_start=week_start, signed_up=0, returned_week_1=0, complete=complete)

    returned: set = set()
    for day, users in activity.items():
        if following_start <= day < following_start + timedelta(days=14):
            returned |= users

    return Cohort(
        week_start=week_start,
        signed_up=len(joined),
        returned_week_1=len(joined & returned),
        complete=complete,
    )


def rate(part: int, whole: int) -> float:
    """Percentage, rounded, guarding the empty case."""
    return 0.0 if whole == 0 else round(part / whole * 100, 1)


def stickiness(daily_active: int, monthly_active: int) -> float:
    """DAU/MAU — what fraction of the monthly audience shows up on a given day.

    The single most honest engagement number: it cannot be inflated by signups
    and drops immediately when people stop coming back.
    """
    return rate(daily_active, monthly_active)
