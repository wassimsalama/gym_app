"""Spec §7.6 — rolling counts and Monday-anchored volume."""

from datetime import date, timedelta

from app.services.config import DEFAULT_WEEKLY_SET_TARGETS, STREAK_WINDOW_DAYS
from app.services.streaks import count_streaks, volume_rings, week_start

# 2026-09-07 is a Monday.
MONDAY = date(2026, 9, 7)


def days_before(anchor: date, offsets: list[int]) -> set[date]:
    return {anchor - timedelta(days=o) for o in offsets}


# --- streaks ---------------------------------------------------------------


def test_nothing_logged_is_zero_not_an_error() -> None:
    result = count_streaks(logged_dates=set(), trained_dates=set(), as_of=MONDAY)
    assert result.logged_14 == 0
    assert result.trained_14 == 0


def test_counts_days_inside_the_window() -> None:
    logged = days_before(MONDAY, [0, 1, 2, 5, 9, 13])
    result = count_streaks(logged_dates=logged, trained_dates=set(), as_of=MONDAY)
    assert result.logged_14 == 6


def test_today_counts_and_the_fifteenth_day_does_not() -> None:
    """The window is inclusive of today and exactly 14 days long."""
    inside = count_streaks(
        logged_dates=days_before(MONDAY, [0, STREAK_WINDOW_DAYS - 1]),
        trained_dates=set(),
        as_of=MONDAY,
    )
    assert inside.logged_14 == 2

    outside = count_streaks(
        logged_dates=days_before(MONDAY, [STREAK_WINDOW_DAYS]),
        trained_dates=set(),
        as_of=MONDAY,
    )
    assert outside.logged_14 == 0


def test_a_gap_does_not_reset_anything() -> None:
    """Spec §2.1: never a zero-reset streak. A missed day costs one day."""
    unbroken = count_streaks(
        logged_dates=days_before(MONDAY, list(range(14))), trained_dates=set(), as_of=MONDAY
    )
    with_gap = count_streaks(
        logged_dates=days_before(MONDAY, [d for d in range(14) if d != 3]),
        trained_dates=set(),
        as_of=MONDAY,
    )
    assert unbroken.logged_14 == 14
    assert with_gap.logged_14 == 13


def test_future_dates_are_not_counted() -> None:
    logged = days_before(MONDAY, [-1, 0, 1])
    result = count_streaks(logged_dates=logged, trained_dates=set(), as_of=MONDAY)
    assert result.logged_14 == 2


def test_trained_and_logged_are_counted_separately() -> None:
    result = count_streaks(
        logged_dates=days_before(MONDAY, list(range(10))),
        trained_dates=days_before(MONDAY, [0, 2, 4]),
        as_of=MONDAY,
    )
    assert result.logged_14 == 10
    assert result.trained_14 == 3


def test_the_window_moves_with_the_reference_date() -> None:
    """A week later, the same history counts for less."""
    logged = days_before(MONDAY, list(range(14)))

    now = count_streaks(logged_dates=logged, trained_dates=set(), as_of=MONDAY)
    later = count_streaks(
        logged_dates=logged, trained_dates=set(), as_of=MONDAY + timedelta(days=7)
    )
    assert now.logged_14 == 14
    assert later.logged_14 == 7


# --- volume rings ----------------------------------------------------------


def test_week_start_is_monday() -> None:
    assert week_start(MONDAY) == MONDAY
    assert week_start(MONDAY + timedelta(days=3)) == MONDAY
    assert week_start(MONDAY + timedelta(days=6)) == MONDAY  # Sunday
    assert week_start(MONDAY + timedelta(days=7)) == MONDAY + timedelta(days=7)


def test_every_targeted_group_appears_even_at_zero() -> None:
    """A leg day that never happened is exactly what needs to be visible."""
    rings = volume_rings(sets_by_group={"chest": 12})

    assert {r.muscle_group for r in rings} >= set(DEFAULT_WEEKLY_SET_TARGETS)
    quads = next(r for r in rings if r.muscle_group == "quads")
    assert quads.sets_this_week == 0
    assert quads.weekly_target == 10


def test_targets_follow_the_config() -> None:
    rings = {r.muscle_group: r.weekly_target for r in volume_rings(sets_by_group={})}
    assert rings["chest"] == 10
    assert rings["biceps"] == 6
    assert rings["core"] == 6


def test_sets_are_reported_per_group() -> None:
    rings = {
        r.muscle_group: r.sets_this_week
        for r in volume_rings(sets_by_group={"chest": 12, "back": 9, "core": 3})
    }
    assert rings["chest"] == 12
    assert rings["back"] == 9
    assert rings["core"] == 3


def test_exceeding_a_target_is_reported_honestly() -> None:
    [chest] = [r for r in volume_rings(sets_by_group={"chest": 25}) if r.muscle_group == "chest"]
    assert chest.sets_this_week == 25
    assert chest.weekly_target == 10


def test_an_untargeted_group_still_shows_its_work() -> None:
    """'other' has no target but the sets were still done."""
    rings = {r.muscle_group: r for r in volume_rings(sets_by_group={"other": 4})}
    assert rings["other"].sets_this_week == 4
    assert rings["other"].weekly_target == 0


def test_targets_can_be_overridden() -> None:
    """Spec §7.6 anticipates these becoming user-configurable."""
    rings = {
        r.muscle_group: r.weekly_target
        for r in volume_rings(sets_by_group={}, targets={"chest": 20})
    }
    assert rings == {"chest": 20}
