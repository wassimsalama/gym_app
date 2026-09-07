"""Spec §7.4 — plateau detection and the cross-stream context that explains it."""

from datetime import date, timedelta

from app.services.plateaus import (
    LOOKBACK_SESSIONS,
    MIN_SESSIONS,
    CalorieContext,
    ExerciseHistory,
    RecoveryContext,
    describe,
    detect,
    is_plateaued,
)

START = date(2026, 9, 1)


def history(e1rms: list[float], *, name: str = "Bench Press", exercise_id: int = 1):
    return ExerciseHistory(
        exercise_id=exercise_id,
        exercise_name=name,
        session_dates=[START + timedelta(days=7 * i) for i in range(len(e1rms))],
        top_e1rms=e1rms,
    )


# --- the flat-patch test ---------------------------------------------------


def test_too_little_history_is_never_a_plateau() -> None:
    """Three flat sessions is a training block, not a stall."""
    assert is_plateaued([120.0] * (MIN_SESSIONS - 1)) is False


def test_four_identical_sessions_is_a_plateau() -> None:
    assert is_plateaued([120.0] * LOOKBACK_SESSIONS) is True


def test_movement_inside_the_threshold_still_counts() -> None:
    """1% of drift is noise, not progress."""
    assert is_plateaued([120.0, 121.0, 119.5, 120.5]) is True


def test_real_progress_is_not_a_plateau() -> None:
    assert is_plateaued([110.0, 115.0, 120.0, 125.0]) is False


def test_only_the_recent_window_matters() -> None:
    """An old stall must not haunt a lift that is moving again."""
    assert is_plateaued([100.0, 100.0, 100.0, 100.0, 110.0, 120.0, 130.0, 140.0]) is False


def test_a_recent_stall_is_caught_despite_old_progress() -> None:
    assert is_plateaued([100.0, 110.0, 120.0, 130.0, 130.0, 130.5, 129.8, 130.2]) is True


def test_zero_history_is_handled() -> None:
    assert is_plateaued([]) is False


# --- context attachment ----------------------------------------------------


def test_a_bare_plateau_says_it_is_a_programming_problem() -> None:
    [plateau] = detect([history([120.0] * 4)])

    assert plateau.calorie is None
    assert plateau.recovery is None
    assert "programming" in describe(plateau)


def test_a_deficit_explains_the_stall() -> None:
    """The spec's own example: cite the numbers, blame the diet, not training."""
    [plateau] = detect(
        [history([120.0] * 4)],
        calorie=CalorieContext(mean_calories=2100.0, tdee_estimate=2500),
    )

    assert plateau.calorie is not None
    message = describe(plateau)
    assert "2100" in message
    assert "2500" in message
    assert "400" in message
    assert "not a training problem" in message


def test_a_trivial_deficit_explains_nothing() -> None:
    """100 kcal under maintenance does not stall a bench press."""
    [plateau] = detect(
        [history([120.0] * 4)],
        calorie=CalorieContext(mean_calories=2400.0, tdee_estimate=2500),
    )
    assert plateau.calorie is None


def test_eating_at_maintenance_attaches_no_calorie_context() -> None:
    [plateau] = detect(
        [history([120.0] * 4)],
        calorie=CalorieContext(mean_calories=2500.0, tdee_estimate=2500),
    )
    assert plateau.calorie is None


def test_a_surplus_never_reads_as_a_deficit() -> None:
    [plateau] = detect(
        [history([120.0] * 4)],
        calorie=CalorieContext(mean_calories=3200.0, tdee_estimate=2500),
    )
    assert plateau.calorie is None


def test_missed_rest_days_explain_the_stall() -> None:
    [plateau] = detect(
        [history([120.0] * 4)],
        recovery=RecoveryContext(rest_days_recent=2, rest_days_typical=5.0),
    )

    assert plateau.recovery is not None
    message = describe(plateau)
    assert "2 rest days" in message
    assert "5.0" in message
    assert "Under-recovery" in message


def test_one_fewer_rest_day_is_within_normal_variation() -> None:
    [plateau] = detect(
        [history([120.0] * 4)],
        recovery=RecoveryContext(rest_days_recent=4, rest_days_typical=5.0),
    )
    assert plateau.recovery is None


def test_extra_rest_is_not_under_recovery() -> None:
    [plateau] = detect(
        [history([120.0] * 4)],
        recovery=RecoveryContext(rest_days_recent=7, rest_days_typical=4.0),
    )
    assert plateau.recovery is None


def test_diet_is_cited_ahead_of_recovery_when_both_apply() -> None:
    """A 400 kcal deficit is the more actionable of the two."""
    [plateau] = detect(
        [history([120.0] * 4)],
        calorie=CalorieContext(mean_calories=2100.0, tdee_estimate=2500),
        recovery=RecoveryContext(rest_days_recent=2, rest_days_typical=5.0),
    )
    assert "maintenance" in describe(plateau)


# --- across several exercises ----------------------------------------------


def test_only_stalled_exercises_are_reported() -> None:
    plateaus = detect(
        [
            history([120.0] * 4, name="Bench Press", exercise_id=1),
            history([100.0, 110.0, 120.0, 130.0], name="Squat", exercise_id=2),
        ]
    )
    assert [p.exercise_name for p in plateaus] == ["Bench Press"]


def test_the_heaviest_stalled_lift_leads() -> None:
    plateaus = detect(
        [
            history([80.0] * 4, name="Curl", exercise_id=1),
            history([180.0] * 4, name="Deadlift", exercise_id=2),
        ]
    )
    assert [p.exercise_name for p in plateaus] == ["Deadlift", "Curl"]


def test_nothing_stalled_reports_nothing() -> None:
    assert detect([history([100.0, 110.0, 120.0, 130.0])]) == []


def test_evidence_carries_the_numbers_used() -> None:
    """§7.5: every suggestion carries the figures behind it."""
    [plateau] = detect(
        [history([120.0, 121.0, 119.5, 120.5])],
        calorie=CalorieContext(mean_calories=2100.0, tdee_estimate=2500),
    )

    assert plateau.evidence["sessions"] == 4
    assert plateau.evidence["best_e1rm_kg"] == 121.0
    assert plateau.evidence["deficit_kcal"] == 400
    assert plateau.evidence["mean_calories"] == 2100
