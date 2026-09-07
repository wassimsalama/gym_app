"""Spec §7.3 — Epley e1RM and PR detection."""

import pytest

from app.services.prs import (
    EPLEY_REP_CAP,
    SetPerformance,
    best_e1rm_per_exercise,
    detect,
    epley_e1rm,
)

BENCH, SQUAT, ROW = 1, 2, 3


def s(exercise_id: int, weight: float, reps: int) -> SetPerformance:
    return SetPerformance(exercise_id=exercise_id, weight_kg=weight, reps=reps)


# --- the formula -----------------------------------------------------------


def test_a_single_rep_is_its_own_max() -> None:
    assert epley_e1rm(100.0, 1) == pytest.approx(100.0 * (1 + 1 / 30))


def test_more_reps_at_the_same_weight_estimate_higher() -> None:
    assert epley_e1rm(100.0, 5) > epley_e1rm(100.0, 3)


def test_reps_are_capped_inside_the_formula() -> None:
    """A 20-rep set must not out-rank a heavy triple through inflation alone."""
    assert epley_e1rm(60.0, 20) == epley_e1rm(60.0, EPLEY_REP_CAP)
    assert epley_e1rm(60.0, 100) == epley_e1rm(60.0, EPLEY_REP_CAP)


def test_the_cap_does_not_bite_below_itself() -> None:
    assert epley_e1rm(100.0, 11) < epley_e1rm(100.0, 12)


def test_nonsense_input_estimates_nothing() -> None:
    assert epley_e1rm(0.0, 5) == 0.0
    assert epley_e1rm(100.0, 0) == 0.0
    assert epley_e1rm(-50.0, 5) == 0.0


def test_a_heavier_top_set_wins_across_rep_ranges() -> None:
    """The whole point of e1RM: rank sets that aren't directly comparable."""
    assert epley_e1rm(110.0, 3) > epley_e1rm(100.0, 5)


# --- best per exercise -----------------------------------------------------


def test_best_picks_the_strongest_set_not_the_last() -> None:
    sets = [s(BENCH, 100, 5), s(BENCH, 110, 3), s(BENCH, 80, 8)]
    assert best_e1rm_per_exercise(sets)[BENCH] == pytest.approx(epley_e1rm(110, 3))


def test_best_keeps_exercises_apart() -> None:
    best = best_e1rm_per_exercise([s(BENCH, 100, 5), s(SQUAT, 140, 5)])
    assert set(best) == {BENCH, SQUAT}
    assert best[SQUAT] > best[BENCH]


def test_best_of_nothing_is_empty() -> None:
    assert best_e1rm_per_exercise([]) == {}


# --- detection -------------------------------------------------------------


def test_beating_the_previous_best_is_a_pr() -> None:
    history = {BENCH: epley_e1rm(100, 5)}
    [pr] = detect([s(BENCH, 105, 5)], history)

    assert pr.exercise_id == BENCH
    assert pr.e1rm == pytest.approx(epley_e1rm(105, 5))
    assert pr.previous_e1rm == pytest.approx(history[BENCH])


def test_a_first_ever_performance_is_not_announced() -> None:
    """Spec §7.3: no baseline, so nothing was beaten."""
    assert detect([s(BENCH, 100, 5)], {}) == []


def test_matching_the_previous_best_is_not_a_pr() -> None:
    """Strictly greater — repeating a lift is not a record."""
    history = {BENCH: epley_e1rm(100, 5)}
    assert detect([s(BENCH, 100, 5)], history) == []


def test_falling_short_is_not_a_pr() -> None:
    history = {BENCH: epley_e1rm(110, 5)}
    assert detect([s(BENCH, 100, 5)], history) == []


def test_only_the_best_set_of_the_session_counts() -> None:
    """A warm-up followed by a PR is one record, not two."""
    history = {BENCH: epley_e1rm(100, 5)}
    prs = detect([s(BENCH, 60, 10), s(BENCH, 105, 5), s(BENCH, 107, 5)], history)

    assert len(prs) == 1
    assert prs[0].e1rm == pytest.approx(epley_e1rm(107, 5))


def test_several_exercises_can_pr_in_one_session() -> None:
    history = {BENCH: epley_e1rm(100, 5), SQUAT: epley_e1rm(140, 5)}
    prs = detect([s(BENCH, 105, 5), s(SQUAT, 145, 5)], history)
    assert {pr.exercise_id for pr in prs} == {BENCH, SQUAT}


def test_prs_lead_with_the_biggest_leap() -> None:
    history = {BENCH: epley_e1rm(100, 5), SQUAT: epley_e1rm(140, 5)}
    prs = detect([s(BENCH, 101, 5), s(SQUAT, 155, 5)], history)
    assert prs[0].exercise_id == SQUAT


def test_an_exercise_with_history_pr_s_beside_a_brand_new_one() -> None:
    history = {BENCH: epley_e1rm(100, 5)}
    prs = detect([s(BENCH, 105, 5), s(ROW, 80, 8)], history)

    assert [pr.exercise_id for pr in prs] == [BENCH]  # the new exercise stays quiet


def test_a_high_rep_set_cannot_pr_through_inflation() -> None:
    """20 reps must be scored as 12, so it cannot fake a record."""
    history = {BENCH: epley_e1rm(100, 12)}
    assert detect([s(BENCH, 100, 20)], history) == []


def test_an_empty_session_sets_no_records() -> None:
    assert detect([], {BENCH: 120.0}) == []
