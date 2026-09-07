"""Total daily energy expenditure, estimated from the user's own data (spec §7.2).

Calculators guess maintenance from height, weight and an activity multiplier
nobody picks honestly. This measures it instead: over a few weeks, the calories
eaten plus the energy the body drew from (or added to) storage is what was
actually spent.

    tdee = mean(calories) − kg_per_day × 7700

7700 kcal is the conventional energy content of a kilogram of body mass. The
slope comes from the *smoothed* weight series — regressing raw weights lets a
single salty dinner shift the estimate by hundreds of calories.

Pure functions over plain data; no ORM types.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.services.smoothing import WeightPoint
from app.services.stats import least_squares_slope

#: How far back to look.
WINDOW_DAYS = 21

#: Days inside the window needing *both* a weight and a calorie figure. Below
#: this the slope is too noisy to divide into a calorie number.
MIN_PAIRED_DAYS = 14

#: kcal per kg of body mass.
KCAL_PER_KG = 7700

#: Outside this range the answer is a data problem, not physiology — someone
#: logged pounds as kilos, or a day's calories twice.
MIN_PLAUSIBLE_KCAL = 1200
MAX_PLAUSIBLE_KCAL = 6000


@dataclass(frozen=True)
class TdeeEstimate:
    estimate_kcal: int | None
    days_of_data: int
    reliable: bool

    @property
    def days_until_reliable(self) -> int:
        return max(0, MIN_PAIRED_DAYS - self.days_of_data)


def estimate(
    points: list[WeightPoint],
    calories_by_date: dict[date, int],
    *,
    as_of: date,
    window_days: int = WINDOW_DAYS,
) -> TdeeEstimate:
    """Estimate maintenance calories over the trailing window.

    Only days carrying both a weight and a calorie entry count towards the
    threshold: a fortnight of weights with no food logged says nothing about
    intake, and vice versa.
    """
    cutoff = as_of - timedelta(days=window_days - 1)
    in_window = [p for p in points if cutoff <= p.date <= as_of]

    paired = [p for p in in_window if p.date in calories_by_date]
    days_of_data = len(paired)

    if days_of_data < MIN_PAIRED_DAYS:
        return TdeeEstimate(estimate_kcal=None, days_of_data=days_of_data, reliable=False)

    # The slope is fitted over every weight in the window, not just paired days
    # — a weight logged on a day food was not is still evidence of the trend.
    origin = in_window[0].date
    slope = least_squares_slope(
        [float((p.date - origin).days) for p in in_window],
        [p.smoothed_kg for p in in_window],
    )
    if slope is None:
        return TdeeEstimate(estimate_kcal=None, days_of_data=days_of_data, reliable=False)

    mean_calories = sum(calories_by_date[p.date] for p in paired) / len(paired)
    raw = mean_calories - slope * KCAL_PER_KG

    if not MIN_PLAUSIBLE_KCAL <= raw <= MAX_PLAUSIBLE_KCAL:
        # Report the number so the user can see what went wrong, but never
        # dress it up as reliable.
        return TdeeEstimate(estimate_kcal=round(raw), days_of_data=days_of_data, reliable=False)

    return TdeeEstimate(estimate_kcal=round(raw), days_of_data=days_of_data, reliable=True)
