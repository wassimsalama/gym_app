"""Spec §7.5 — ranking, the cap, and the rule that every message cites numbers."""

import re

from app.services.plateaus import CalorieContext, ExerciseHistory, detect
from app.services.streaks import VolumeRing
from app.services.suggestions import (
    LOGGING_NUDGE_THRESHOLD,
    MAX_SUGGESTIONS,
    PRIORITY,
    Suggestion,
    assemble,
    from_goal,
    from_logging,
    from_plateaus,
    from_tdee,
    from_volume,
)
from app.services.tdee import TdeeEstimate

RELIABLE = TdeeEstimate(estimate_kcal=2500, days_of_data=21, reliable=True)


def stalled(name: str = "Bench Press", exercise_id: int = 1, e1rm: float = 120.0):
    return ExerciseHistory(
        exercise_id=exercise_id, exercise_name=name, session_dates=[], top_e1rms=[e1rm] * 4
    )


# --- individual producers --------------------------------------------------


def test_tdee_says_nothing_until_it_is_reliable() -> None:
    unreliable = TdeeEstimate(estimate_kcal=None, days_of_data=5, reliable=False)
    assert from_tdee(unreliable, 2000.0) == []


def test_tdee_reports_the_deficit_and_its_consequence() -> None:
    [s] = from_tdee(RELIABLE, 2000.0)

    assert s.kind == "tdee_update"
    assert "2500" in s.message
    assert "500 kcal under maintenance" in s.message
    assert s.evidence["projected_weekly_kg"] < 0


def test_tdee_reports_a_surplus_too() -> None:
    [s] = from_tdee(RELIABLE, 3000.0)
    assert "over maintenance" in s.message
    assert s.evidence["projected_weekly_kg"] > 0


def test_volume_stays_quiet_before_the_week_has_started() -> None:
    """Zero legs on Monday morning is not news."""
    rings = [VolumeRing(muscle_group="quads", sets_this_week=0, weekly_target=10)]
    assert from_volume(rings, trained_this_week=False) == []


def test_volume_flags_the_group_furthest_behind() -> None:
    rings = [
        VolumeRing(muscle_group="chest", sets_this_week=9, weekly_target=10),
        VolumeRing(muscle_group="quads", sets_this_week=2, weekly_target=10),
    ]
    [s] = from_volume(rings, trained_this_week=True)

    assert s.evidence["muscle_group"] == "quads"
    assert "20%" in s.message
    assert "2 of 10" in s.message


def test_volume_says_nothing_when_everything_is_on_track() -> None:
    rings = [VolumeRing(muscle_group="chest", sets_this_week=8, weekly_target=10)]
    assert from_volume(rings, trained_this_week=True) == []


def test_untargeted_groups_are_never_flagged() -> None:
    rings = [VolumeRing(muscle_group="other", sets_this_week=0, weekly_target=0)]
    assert from_volume(rings, trained_this_week=True) == []


def test_goal_speaks_only_with_both_a_projection_and_a_target() -> None:
    assert (
        from_goal(progress_pct=40.0, projected_date=None, target_date="2026-12-01", on_track=None)
        == []
    )
    assert (
        from_goal(progress_pct=40.0, projected_date="2026-12-05", target_date=None, on_track=None)
        == []
    )


def test_goal_reports_being_behind() -> None:
    [s] = from_goal(
        progress_pct=40.0, projected_date="2026-12-20", target_date="2026-12-01", on_track=False
    )
    assert "later than" in s.message
    assert "2026-12-20" in s.message


def test_goal_reports_being_ahead() -> None:
    [s] = from_goal(
        progress_pct=40.0, projected_date="2026-11-20", target_date="2026-12-01", on_track=True
    )
    assert "ahead of" in s.message


def test_logging_nudge_only_when_data_is_thin() -> None:
    assert from_logging(logged_14=LOGGING_NUDGE_THRESHOLD) == []
    [s] = from_logging(logged_14=2)
    assert "2 of the last 14" in s.message


# --- assembly --------------------------------------------------------------


def test_priority_order_is_respected() -> None:
    everything = assemble(
        from_logging(logged_14=1),
        from_goal(
            progress_pct=40.0, projected_date="2026-12-20", target_date="2026-12-01", on_track=False
        ),
        from_volume(
            [VolumeRing(muscle_group="quads", sets_this_week=1, weekly_target=10)],
            trained_this_week=True,
        ),
        from_tdee(RELIABLE, 2000.0),
        from_plateaus(detect([stalled()])),
        limit=99,
    )
    kinds = [s.kind for s in everything]
    assert kinds == sorted(kinds, key=PRIORITY.index)
    assert kinds[0] == "plateau"


def test_never_more_than_three() -> None:
    """A list of nine suggestions is a list of none."""
    everything = assemble(
        from_plateaus(detect([stalled("A", 1, 100), stalled("B", 2, 110), stalled("C", 3, 120)])),
        from_tdee(RELIABLE, 2000.0),
        from_logging(logged_14=1),
    )
    assert len(everything) == MAX_SUGGESTIONS


def test_the_cap_drops_the_least_important() -> None:
    """Five candidates, three slots — the bottom two must be the ones to go."""
    everything = assemble(
        from_logging(logged_14=1),
        from_goal(
            progress_pct=40.0, projected_date="2026-12-20", target_date="2026-12-01", on_track=False
        ),
        from_volume(
            [VolumeRing(muscle_group="quads", sets_this_week=1, weekly_target=10)],
            trained_this_week=True,
        ),
        from_plateaus(detect([stalled()])),
        from_tdee(RELIABLE, 2000.0),
    )

    assert [s.kind for s in everything] == ["plateau", "tdee_update", "volume_gap"]
    assert "goal_projection" not in [s.kind for s in everything]
    assert "logging_nudge" not in [s.kind for s in everything]


def test_several_plateaus_keep_the_heaviest_first() -> None:
    everything = assemble(
        from_plateaus(detect([stalled("Curl", 1, 60.0), stalled("Deadlift", 2, 200.0)])),
        limit=99,
    )
    assert [s.message.split()[0] for s in everything] == ["Deadlift", "Curl"]


def test_nothing_to_say_is_an_empty_list() -> None:
    """No filler. An app with nothing useful says nothing."""
    assert assemble([], [], []) == []


# --- the no-praise rule ----------------------------------------------------


def test_every_message_contains_a_number() -> None:
    """§7.5: suggestions cite their evidence. A message with no figure in it is
    exactly the generic encouragement the spec forbids."""
    everything = assemble(
        from_plateaus(
            detect([stalled()], calorie=CalorieContext(mean_calories=2100.0, tdee_estimate=2500))
        ),
        from_tdee(RELIABLE, 2000.0),
        from_volume(
            [VolumeRing(muscle_group="quads", sets_this_week=1, weekly_target=10)],
            trained_this_week=True,
        ),
        from_goal(
            progress_pct=40.0, projected_date="2026-12-20", target_date="2026-12-01", on_track=False
        ),
        from_logging(logged_14=2),
        limit=99,
    )
    assert everything
    for suggestion in everything:
        assert re.search(r"\d", suggestion.message), suggestion.message
        assert suggestion.evidence, suggestion.kind


def test_no_praise_vocabulary_anywhere() -> None:
    banned = ("great job", "well done", "keep it up", "amazing", "awesome", "crushing it")
    everything = assemble(
        from_plateaus(detect([stalled()])),
        from_tdee(RELIABLE, 2500.0),
        from_goal(
            progress_pct=90.0, projected_date="2026-11-01", target_date="2026-12-01", on_track=True
        ),
        limit=99,
    )
    for suggestion in everything:
        lowered = suggestion.message.lower()
        assert not any(phrase in lowered for phrase in banned), suggestion.message


def test_ids_are_stable_so_the_app_can_dismiss_them() -> None:
    first = assemble(from_plateaus(detect([stalled()])))
    again = assemble(from_plateaus(detect([stalled()])))
    assert [s.id for s in first] == [s.id for s in again]


def test_suggestion_is_immutable() -> None:
    s = Suggestion(id="x", kind="plateau", message="m")
    try:
        s.kind = "other"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Suggestion should be frozen")
