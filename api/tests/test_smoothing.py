"""Spec §7.1 — including every edge case the spec calls out by name."""

from datetime import date, timedelta

import pytest

from app.services.smoothing import (
    MIN_POINTS_FOR_AVERAGE,
    WINDOW_DAYS,
    WeightPoint,
    latest_smoothed,
    smooth_series,
)

START = date(2026, 9, 1)


def days(*offsets: int) -> list[date]:
    return [START + timedelta(days=o) for o in offsets]


def series(pairs: list[tuple[int, float]]) -> list[tuple[date, float]]:
    return [(START + timedelta(days=o), w) for o, w in pairs]


def test_empty_series_returns_empty() -> None:
    assert smooth_series([]) == []


def test_single_point_is_its_own_value() -> None:
    [point] = smooth_series(series([(0, 80.0)]))
    assert point.raw_kg == 80.0
    assert point.smoothed_kg == 80.0


@pytest.mark.parametrize("count", [1, 2])
def test_below_the_minimum_the_raw_value_passes_through(count: int) -> None:
    """Spec: < 3 points in window -> smoothed = raw."""
    assert count < MIN_POINTS_FOR_AVERAGE
    points = smooth_series(series([(i, 80.0 + i) for i in range(count)]))
    for point in points:
        assert point.smoothed_kg == point.raw_kg


def test_third_point_starts_averaging() -> None:
    points = smooth_series(series([(0, 80.0), (1, 82.0), (2, 84.0)]))
    assert points[0].smoothed_kg == 80.0  # 1 in window
    assert points[1].smoothed_kg == 82.0  # 2 in window
    assert points[2].smoothed_kg == pytest.approx(82.0)  # (80+82+84)/3


def test_window_is_trailing_not_centred() -> None:
    """A point is never smoothed using values from its future."""
    points = smooth_series(series([(0, 80.0), (1, 80.0), (2, 80.0), (3, 100.0)]))
    assert points[2].smoothed_kg == pytest.approx(80.0)
    assert points[3].smoothed_kg == pytest.approx((80 + 80 + 80 + 100) / 4)


def test_window_excludes_points_older_than_the_window() -> None:
    """The 8th day must drop the 1st — WINDOW_DAYS is inclusive of today."""
    pairs = [(i, 80.0) for i in range(WINDOW_DAYS)] + [(WINDOW_DAYS, 100.0)]
    points = smooth_series(series(pairs))
    # Day 7 sees days 1..7 (six 80s plus the 100), not day 0.
    assert points[-1].smoothed_kg == pytest.approx((80.0 * 6 + 100.0) / 7)


def test_gaps_do_not_require_contiguous_days() -> None:
    """Spec: average what exists in the window, don't demand contiguity."""
    points = smooth_series(series([(0, 80.0), (3, 82.0), (6, 84.0)]))
    assert points[-1].smoothed_kg == pytest.approx(82.0)


def test_a_long_gap_does_not_average_across_it() -> None:
    """After a fortnight away, the window holds only the new point."""
    points = smooth_series(series([(0, 80.0), (1, 80.0), (2, 80.0), (30, 90.0)]))
    assert points[-1].smoothed_kg == 90.0


def test_all_identical_weights_smooth_to_that_weight() -> None:
    points = smooth_series(series([(i, 80.0) for i in range(10)]))
    assert all(p.smoothed_kg == pytest.approx(80.0) for p in points)


def test_a_single_outlier_is_damped_not_followed() -> None:
    """The whole point of smoothing: one bad morning must not move the line far."""
    pairs = [(i, 80.0) for i in range(6)] + [(6, 86.0)]
    points = smooth_series(series(pairs))
    spike = points[-1]
    assert spike.raw_kg == 86.0
    # Averaged against six 80s, the 6 kg jump shows up as under 1 kg.
    assert spike.smoothed_kg == pytest.approx((80.0 * 6 + 86.0) / 7)
    assert spike.smoothed_kg - 80.0 < 1.0


def test_unordered_input_is_sorted_before_smoothing() -> None:
    shuffled = series([(2, 84.0), (0, 80.0), (1, 82.0)])
    points = smooth_series(shuffled)
    assert [p.date for p in points] == days(0, 1, 2)
    assert points[-1].smoothed_kg == pytest.approx(82.0)


def test_raw_values_are_preserved_alongside_the_trend() -> None:
    points = smooth_series(series([(0, 80.0), (1, 90.0), (2, 70.0)]))
    assert [p.raw_kg for p in points] == [80.0, 90.0, 70.0]


def test_latest_smoothed_reads_the_final_point() -> None:
    points = smooth_series(series([(0, 80.0), (1, 82.0), (2, 84.0)]))
    assert latest_smoothed(points) == pytest.approx(82.0)


def test_latest_smoothed_of_nothing_is_none() -> None:
    assert latest_smoothed([]) is None


def test_weight_point_is_immutable() -> None:
    point = WeightPoint(date=START, raw_kg=80.0, smoothed_kg=80.0)
    with pytest.raises(AttributeError):
        point.raw_kg = 81.0  # type: ignore[misc]
