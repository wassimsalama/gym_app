"""Goal progress and projection.

The governing rule (spec §2.6): status comes from the trend, not from wishful
maths. Most of these cases assert that a projection is *refused*.
"""

from datetime import date, timedelta

import pytest

from app.services.projection import (
    GOAL_TOLERANCE_KG,
    MAX_PROJECTION_DAYS,
    evaluate,
    progress_pct,
    project_goal_date,
    trend_slope_kg_per_day,
)
from app.services.smoothing import smooth_series
from app.services.stats import least_squares_slope

START = date(2026, 9, 1)


def losing(days: int, per_day: float = 0.1, from_kg: float = 90.0):
    """A clean linear cut, one weigh-in per day."""
    return smooth_series([(START + timedelta(days=i), from_kg - per_day * i) for i in range(days)])


# --- least squares ---------------------------------------------------------


def test_slope_of_a_straight_line() -> None:
    assert least_squares_slope([0, 1, 2, 3], [0, 2, 4, 6]) == pytest.approx(2.0)


def test_slope_of_a_flat_line_is_zero() -> None:
    assert least_squares_slope([0, 1, 2], [5, 5, 5]) == pytest.approx(0.0)


def test_slope_is_undefined_below_two_points() -> None:
    assert least_squares_slope([1], [1]) is None
    assert least_squares_slope([], []) is None


def test_slope_is_undefined_when_every_x_is_identical() -> None:
    assert least_squares_slope([2, 2, 2], [1, 2, 3]) is None


def test_slope_rejects_mismatched_lengths() -> None:
    assert least_squares_slope([0, 1, 2], [0, 1]) is None


# --- progress --------------------------------------------------------------


def test_progress_at_the_start_is_zero() -> None:
    assert progress_pct(90.0, 80.0, 90.0) == pytest.approx(0.0)


def test_progress_at_the_goal_is_one_hundred() -> None:
    assert progress_pct(90.0, 80.0, 80.0) == pytest.approx(100.0)


def test_progress_halfway() -> None:
    assert progress_pct(90.0, 80.0, 85.0) == pytest.approx(50.0)


def test_progress_works_for_gaining_as_well_as_cutting() -> None:
    assert progress_pct(70.0, 80.0, 75.0) == pytest.approx(50.0)


def test_progress_clamps_when_moving_the_wrong_way() -> None:
    """A progress bar cannot draw -30%."""
    assert progress_pct(90.0, 80.0, 93.0) == 0.0


def test_progress_clamps_when_overshooting() -> None:
    assert progress_pct(90.0, 80.0, 75.0) == 100.0


def test_progress_when_start_equals_goal() -> None:
    """Degenerate but reachable via onboarding; must not divide by zero."""
    assert progress_pct(80.0, 80.0, 80.0) == 100.0


# --- projection ------------------------------------------------------------


def test_projects_a_date_from_a_steady_cut() -> None:
    """0.1 kg/day with 5 kg to go lands ~50 days out."""
    projected = project_goal_date(85.0, 80.0, -0.1, as_of=START)
    assert projected == START + timedelta(days=50)


def test_projects_for_a_bulk_too() -> None:
    projected = project_goal_date(75.0, 80.0, 0.1, as_of=START)
    assert projected == START + timedelta(days=50)


def test_no_projection_when_the_trend_points_away_from_the_goal() -> None:
    """Gaining while trying to cut must not produce a date."""
    assert project_goal_date(85.0, 80.0, +0.1, as_of=START) is None


def test_no_projection_from_a_flat_trend() -> None:
    assert project_goal_date(85.0, 80.0, 0.0, as_of=START) is None


def test_no_projection_from_an_imperceptible_trend() -> None:
    """0.001 kg/day would project 13 years out — refuse rather than flatter."""
    assert project_goal_date(85.0, 80.0, -0.001, as_of=START) is None


def test_no_projection_without_a_slope() -> None:
    assert project_goal_date(85.0, 80.0, None, as_of=START) is None


def test_no_projection_beyond_the_horizon() -> None:
    """30 kg at 0.01 kg/day is 3000 days — not actionable information."""
    assert project_goal_date(110.0, 80.0, -0.01, as_of=START) is None


def test_projection_exactly_at_the_horizon_is_allowed() -> None:
    slope = -1.0
    projected = project_goal_date(80.0 + MAX_PROJECTION_DAYS * 1.0, 80.0, slope, as_of=START)
    assert projected == START + timedelta(days=MAX_PROJECTION_DAYS)


def test_goal_already_reached_projects_today() -> None:
    assert project_goal_date(80.0, 80.0, -0.1, as_of=START) == START
    assert project_goal_date(80.0 + GOAL_TOLERANCE_KG / 2, 80.0, None, as_of=START) == START


# --- trend slope over the window -------------------------------------------


def test_trend_slope_tracks_a_linear_cut() -> None:
    points = losing(14)
    slope = trend_slope_kg_per_day(points, as_of=points[-1].date)
    assert slope is not None
    assert slope < 0


def test_trend_slope_needs_at_least_two_points() -> None:
    points = losing(1)
    assert trend_slope_kg_per_day(points, as_of=points[-1].date) is None


def test_trend_slope_ignores_points_outside_the_window() -> None:
    """Weights from months ago must not drag the current trend."""
    old = [(START + timedelta(days=i), 120.0) for i in range(3)]
    recent = [(START + timedelta(days=200 + i), 90.0 - 0.1 * i) for i in range(10)]
    points = smooth_series(old + recent)

    slope = trend_slope_kg_per_day(points, as_of=points[-1].date)
    assert slope is not None
    assert slope == pytest.approx(-0.1, abs=0.05)


# --- the assembled block ---------------------------------------------------


def test_evaluate_reports_progress_and_a_date() -> None:
    points = losing(21)
    result = evaluate(start_kg=90.0, goal_kg=80.0, points=points, as_of=points[-1].date)

    assert 0 < result.progress_pct < 100
    assert result.projected_date is not None
    assert result.on_track is None  # no target date supplied


def test_evaluate_is_on_track_when_the_projection_beats_the_target() -> None:
    points = losing(21)
    as_of = points[-1].date
    result = evaluate(
        start_kg=90.0,
        goal_kg=80.0,
        points=points,
        as_of=as_of,
        target_date=as_of + timedelta(days=365),
    )
    assert result.on_track is True


def test_evaluate_is_off_track_when_the_target_is_sooner_than_the_trend() -> None:
    points = losing(21)
    as_of = points[-1].date
    result = evaluate(
        start_kg=90.0,
        goal_kg=80.0,
        points=points,
        as_of=as_of,
        target_date=as_of + timedelta(days=2),
    )
    assert result.on_track is False


def test_evaluate_refuses_a_verdict_when_the_trend_is_flat() -> None:
    """A target date alone does not license an on/off-track claim."""
    flat = smooth_series([(START + timedelta(days=i), 90.0) for i in range(21)])
    result = evaluate(
        start_kg=90.0,
        goal_kg=80.0,
        points=flat,
        as_of=flat[-1].date,
        target_date=flat[-1].date + timedelta(days=30),
    )
    assert result.projected_date is None
    assert result.on_track is None
    assert result.progress_pct == 0.0


def test_evaluate_with_no_observations_falls_back_to_the_start_weight() -> None:
    result = evaluate(start_kg=90.0, goal_kg=80.0, points=[], as_of=START)
    assert result.progress_pct == 0.0
    assert result.projected_date is None
    assert result.on_track is None
