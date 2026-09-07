"""Spec §7.7 — the last *completed* Monday–Sunday week."""

from datetime import date, timedelta

from app.services.recap import BestLift, build, last_completed_week

# 2026-09-28 is a Monday; 2026-10-04 is the Sunday that closes that week.
MONDAY = date(2026, 9, 28)
SUNDAY = date(2026, 10, 4)


def week_days() -> list[date]:
    return [MONDAY + timedelta(days=i) for i in range(7)]


# --- which week ------------------------------------------------------------


def test_midweek_looks_back_to_the_previous_week() -> None:
    wednesday = MONDAY + timedelta(days=9)
    assert last_completed_week(wednesday) == (MONDAY, SUNDAY)


def test_on_a_sunday_the_current_week_is_not_yet_over() -> None:
    """A recap that keeps changing through the day is not a recap."""
    assert last_completed_week(SUNDAY) == (MONDAY - timedelta(days=7), MONDAY - timedelta(days=1))


def test_on_a_monday_the_week_just_finished_is_reported() -> None:
    next_monday = MONDAY + timedelta(days=7)
    assert last_completed_week(next_monday) == (MONDAY, SUNDAY)


# --- the numbers -----------------------------------------------------------


def base(**overrides):
    args = {
        "as_of": MONDAY + timedelta(days=9),
        "session_dates": [],
        "set_volumes": [],
        "logged_dates": set(),
        "trained_dates": set(),
        "smoothed_start": None,
        "smoothed_end": None,
        "best_lift": None,
    }
    args.update(overrides)
    return build(**args)


def test_an_empty_week_reports_zeroes_not_nulls() -> None:
    recap = base()

    assert recap.week_start == MONDAY
    assert recap.week_end == SUNDAY
    assert recap.sessions == 0
    assert recap.total_sets == 0
    assert recap.total_volume_kg == 0
    assert recap.weight_delta_kg is None
    assert recap.best_lift is None


def test_sessions_outside_the_week_are_excluded() -> None:
    recap = base(
        session_dates=[
            MONDAY - timedelta(days=1),  # the Sunday before
            MONDAY,
            MONDAY + timedelta(days=3),
            SUNDAY,
            SUNDAY + timedelta(days=1),  # the Monday after
        ]
    )
    assert recap.sessions == 3


def test_volume_is_weight_times_reps() -> None:
    recap = base(set_volumes=[(100.0, 5), (100.0, 5), (60.0, 10)])

    assert recap.total_sets == 3
    assert recap.total_volume_kg == 100 * 5 + 100 * 5 + 60 * 10


def test_weight_delta_uses_the_smoothed_line() -> None:
    recap = base(smoothed_start=90.0, smoothed_end=89.2)
    assert recap.weight_delta_kg is not None
    assert round(recap.weight_delta_kg, 2) == -0.8


def test_weight_delta_is_null_without_both_ends() -> None:
    assert base(smoothed_start=90.0).weight_delta_kg is None
    assert base(smoothed_end=90.0).weight_delta_kg is None


def test_day_counts_are_scoped_to_the_week() -> None:
    recap = base(
        logged_dates=set(week_days()) | {MONDAY - timedelta(days=2)},
        trained_dates={MONDAY, MONDAY + timedelta(days=2), SUNDAY + timedelta(days=5)},
    )
    assert recap.days_logged == 7
    assert recap.days_trained == 2


def test_a_best_lift_that_beat_its_previous_max_is_a_record() -> None:
    lift = BestLift(exercise_id=1, exercise_name="Bench Press", e1rm=122.5, previous_best=119.6)
    assert base(best_lift=lift).best_lift.was_a_record is True


def test_a_best_lift_with_no_history_is_not_a_record() -> None:
    lift = BestLift(exercise_id=1, exercise_name="Bench Press", e1rm=122.5, previous_best=None)
    assert base(best_lift=lift).best_lift.was_a_record is False


def test_the_weeks_best_need_not_be_a_record() -> None:
    """Your heaviest set of the week can still be under your all-time best."""
    lift = BestLift(exercise_id=1, exercise_name="Bench Press", e1rm=110.0, previous_best=125.0)
    assert base(best_lift=lift).best_lift.was_a_record is False
