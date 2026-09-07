"""Weight smoothing (spec §7.1).

Raw daily bodyweight swings by a kilo or more on water alone. Showing that
unsmoothed makes a successful cut look like failure every other morning, so the
trend line is what the user is shown and what every downstream calculation
(TDEE, projections) consumes.

Pure functions over plain data — no ORM types — so they are unit-testable in
isolation.
"""

from dataclasses import dataclass
from datetime import date, timedelta

#: Trailing window, in days, including the point itself.
WINDOW_DAYS = 7

#: Below this many observations in the window an average is noise dressed up as
#: signal, so the raw value is passed through unchanged.
MIN_POINTS_FOR_AVERAGE = 3


@dataclass(frozen=True)
class WeightPoint:
    """One observed weight. `smoothed` equals `raw` when the window is too thin."""

    date: date
    raw_kg: float
    smoothed_kg: float


def smooth_series(observations: list[tuple[date, float]]) -> list[WeightPoint]:
    """Trailing `WINDOW_DAYS`-day moving average over whatever points exist.

    Gaps are expected — people miss days — so the window is defined by *dates*
    rather than by position, and averages however many observations fall inside
    it. A fortnight's gap therefore does not silently average across it.
    """
    if not observations:
        return []

    ordered = sorted(observations, key=lambda item: item[0])
    points: list[WeightPoint] = []

    for index, (day, raw) in enumerate(ordered):
        window_start = day - timedelta(days=WINDOW_DAYS - 1)

        # Walk back from the current point while still inside the window.
        in_window = [raw]
        for previous_day, previous_raw in reversed(ordered[:index]):
            if previous_day < window_start:
                break
            in_window.append(previous_raw)

        smoothed = (
            sum(in_window) / len(in_window) if len(in_window) >= MIN_POINTS_FOR_AVERAGE else raw
        )
        points.append(WeightPoint(date=day, raw_kg=raw, smoothed_kg=smoothed))

    return points


def latest_smoothed(points: list[WeightPoint]) -> float | None:
    """The current trend value — what "you weigh X" should report."""
    return points[-1].smoothed_kg if points else None
