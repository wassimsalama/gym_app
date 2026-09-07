"""Spec §7.2 — including the edge cases the spec names: gaps in logging,
all-same weights, and a single outlier day."""

from datetime import date, timedelta

from app.services.smoothing import smooth_series
from app.services.tdee import (
    KCAL_PER_KG,
    MIN_PAIRED_DAYS,
    estimate,
)

START = date(2026, 9, 1)

#: History long enough that the 21-day window sits past the smoothing ramp.
#: The 7-day average needs about six days to warm up; a window starting at the
#: very first weigh-in carries that ramp and reads flatter than reality.
WARMED = 35


def build(
    days: int,
    *,
    start_kg: float = 90.0,
    per_day: float = 0.0,
    kcal: int | None = 2500,
    skip: set[int] | None = None,
    kcal_overrides: dict[int, int] | None = None,
):
    """A run of days with weights and (optionally) calories."""
    skip = skip or set()
    observations, calories = [], {}
    for i in range(days):
        if i in skip:
            continue
        day = START + timedelta(days=i)
        observations.append((day, start_kg + per_day * i))
        if kcal is not None:
            calories[day] = (kcal_overrides or {}).get(i, kcal)
    return smooth_series(observations), calories


def as_of(days: int) -> date:
    return START + timedelta(days=days - 1)


def test_too_little_data_reports_null_not_a_guess() -> None:
    points, calories = build(10)
    result = estimate(points, calories, as_of=as_of(10))

    assert result.estimate_kcal is None
    assert result.reliable is False
    assert result.days_of_data == 10


def test_it_says_how_many_days_remain() -> None:
    points, calories = build(10)
    result = estimate(points, calories, as_of=as_of(10))
    assert result.days_until_reliable == MIN_PAIRED_DAYS - 10


def test_nothing_logged_at_all() -> None:
    result = estimate([], {}, as_of=START)
    assert result.estimate_kcal is None
    assert result.days_of_data == 0
    assert result.days_until_reliable == MIN_PAIRED_DAYS


def test_stable_weight_means_intake_is_maintenance() -> None:
    """The cleanest case: weight flat on 2500 kcal, so 2500 is maintenance."""
    points, calories = build(WARMED, per_day=0.0, kcal=2500)
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.reliable is True
    assert result.estimate_kcal == 2500


def test_losing_weight_means_maintenance_is_above_intake() -> None:
    """0.1 kg/day lost on 2000 kcal implies ~770 kcal/day came from storage."""
    points, calories = build(WARMED, per_day=-0.1, kcal=2000)
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.reliable is True
    assert result.estimate_kcal == 2000 + round(0.1 * KCAL_PER_KG)


def test_gaining_weight_means_maintenance_is_below_intake() -> None:
    points, calories = build(WARMED, per_day=0.05, kcal=3200)
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.reliable is True
    assert result.estimate_kcal == 3200 - round(0.05 * KCAL_PER_KG)


def test_gaps_in_logging_are_tolerated() -> None:
    """Spec edge case: missed days must not break the estimate."""
    points, calories = build(WARMED, per_day=-0.1, kcal=2000, skip={25, 29, 31})
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.days_of_data == 18
    assert result.reliable is True


def test_dropping_below_the_threshold_through_gaps_is_unreliable() -> None:
    points, calories = build(WARMED, per_day=-0.1, kcal=2000, skip=set(range(0, WARMED, 2)))
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.days_of_data < MIN_PAIRED_DAYS
    assert result.reliable is False
    assert result.estimate_kcal is None


def test_weights_without_calories_do_not_count() -> None:
    """A fortnight of weigh-ins says nothing about intake."""
    points, _ = build(WARMED, per_day=-0.1)
    result = estimate(points, {}, as_of=as_of(WARMED))

    assert result.days_of_data == 0
    assert result.estimate_kcal is None


def test_a_single_outlier_day_does_not_dominate() -> None:
    """Spec edge case. One 6000 kcal day in three weeks moves the mean by
    about 170 kcal — visible, but not a different answer."""
    points, clean = build(WARMED, per_day=-0.1, kcal=2000)
    _, spiked = build(WARMED, per_day=-0.1, kcal=2000, kcal_overrides={25: 6000})

    baseline = estimate(points, clean, as_of=as_of(WARMED)).estimate_kcal
    spiked_result = estimate(points, spiked, as_of=as_of(WARMED)).estimate_kcal

    assert baseline is not None and spiked_result is not None
    assert 0 < spiked_result - baseline < 250


def test_only_the_window_counts() -> None:
    """Data from two months ago must not drag the current estimate."""
    old_points, old_calories = build(WARMED, start_kg=110.0, per_day=0.0, kcal=4000)
    recent_start = START + timedelta(days=90)

    observations = [(p.date, p.raw_kg) for p in old_points]
    calories = dict(old_calories)
    for i in range(WARMED):
        day = recent_start + timedelta(days=i)
        observations.append((day, 90.0 - 0.1 * i))
        calories[day] = 2000

    points = smooth_series(observations)
    result = estimate(points, calories, as_of=recent_start + timedelta(days=WARMED - 1))

    assert result.days_of_data == 21
    assert result.estimate_kcal == 2000 + round(0.1 * KCAL_PER_KG)


def test_an_implausible_result_is_reported_but_never_trusted() -> None:
    """A logging error, not physiology — show it so the cause is visible."""
    points, calories = build(WARMED, per_day=-0.6, kcal=2000)  # implies ~6620 kcal
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.estimate_kcal is not None
    assert result.reliable is False


def test_an_absurdly_low_result_is_also_untrusted() -> None:
    points, calories = build(WARMED, per_day=0.5, kcal=1500)
    result = estimate(points, calories, as_of=as_of(WARMED))

    assert result.reliable is False


def test_the_boundary_of_reliability() -> None:
    """Exactly MIN_PAIRED_DAYS is enough; one fewer is not."""
    points, calories = build(MIN_PAIRED_DAYS, per_day=-0.1, kcal=2000)
    assert estimate(points, calories, as_of=as_of(MIN_PAIRED_DAYS)).reliable is True

    points, calories = build(MIN_PAIRED_DAYS - 1, per_day=-0.1, kcal=2000)
    assert estimate(points, calories, as_of=as_of(MIN_PAIRED_DAYS - 1)).reliable is False


def test_a_brand_new_user_reads_slightly_conservative() -> None:
    """A documented limitation, not a defect.

    The 7-day average needs about six days to warm up. Someone whose entire
    history *is* the 21-day window carries that ramp inside it, so the fitted
    slope is flatter than reality and the estimate lands under 150 kcal low. It
    resolves itself within a week of further logging, and understating
    maintenance is the safer direction to be wrong in.
    """
    fresh_points, fresh_calories = build(21, per_day=-0.1, kcal=2000)
    fresh = estimate(fresh_points, fresh_calories, as_of=as_of(21)).estimate_kcal

    settled_points, settled_calories = build(WARMED, per_day=-0.1, kcal=2000)
    settled = estimate(settled_points, settled_calories, as_of=as_of(WARMED)).estimate_kcal

    exact = 2000 + round(0.1 * KCAL_PER_KG)
    assert settled == exact
    assert fresh is not None
    assert 0 < exact - fresh < 150
