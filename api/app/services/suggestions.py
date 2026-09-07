"""Assembling the dashboard's suggestions (spec §7.5).

Two rules do most of the work here.

*Every suggestion carries its evidence.* "You've plateaued" is a horoscope;
"stalled four sessions while averaging 400 kcal under maintenance" is something
a person can act on. There are no generic praise strings anywhere in this
module, by design — an app that congratulates you for opening it teaches you to
ignore everything it says.

*At most three.* A list of nine suggestions is a list of none.
"""

from dataclasses import dataclass, field

from app.services.plateaus import Plateau
from app.services.plateaus import describe as describe_plateau
from app.services.streaks import VolumeRing
from app.services.tdee import TdeeEstimate

#: Highest priority first (spec §7.5).
PRIORITY = ("plateau", "tdee_update", "volume_gap", "goal_projection", "logging_nudge")

MAX_SUGGESTIONS = 3

#: A ring this far short of target is worth mentioning; nearer than this is
#: within the noise of one missed session.
VOLUME_GAP_FRACTION = 0.6

#: Below this many logged days in the fortnight, the numbers stop meaning much
#: and the useful advice is simply to log more.
LOGGING_NUDGE_THRESHOLD = 7


@dataclass(frozen=True)
class Suggestion:
    id: str
    kind: str
    message: str
    evidence: dict = field(default_factory=dict)


def _priority(kind: str) -> int:
    return PRIORITY.index(kind) if kind in PRIORITY else len(PRIORITY)


def from_plateaus(plateaus: list[Plateau]) -> list[Suggestion]:
    return [
        Suggestion(
            id=f"plateau-{p.exercise_id}",
            kind="plateau",
            message=describe_plateau(p),
            evidence=p.evidence,
        )
        for p in plateaus
    ]


def from_tdee(estimate: TdeeEstimate, mean_calories: float | None) -> list[Suggestion]:
    """Report maintenance once it is trustworthy, and say what intake implies."""
    if not estimate.reliable or estimate.estimate_kcal is None or mean_calories is None:
        return []

    difference = mean_calories - estimate.estimate_kcal
    weekly_kg = difference * 7 / 7700

    if difference < 0:
        direction = (
            f"about {abs(round(difference))} kcal under maintenance, "
            f"roughly {abs(weekly_kg):.2f} kg a week down"
        )
    elif difference > 0:
        direction = (
            f"about {round(difference)} kcal over maintenance, roughly {weekly_kg:.2f} kg a week up"
        )
    else:
        direction = "right at maintenance"

    return [
        Suggestion(
            id="tdee",
            kind="tdee_update",
            message=(
                f"Your maintenance is around {estimate.estimate_kcal} kcal, measured from "
                f"{estimate.days_of_data} days of your own weight and intake. You are eating "
                f"{direction}."
            ),
            evidence={
                "tdee_estimate": estimate.estimate_kcal,
                "mean_calories": round(mean_calories),
                "days_of_data": estimate.days_of_data,
                "projected_weekly_kg": round(weekly_kg, 2),
            },
        )
    ]


def from_volume(rings: list[VolumeRing], *, trained_this_week: bool) -> list[Suggestion]:
    """Flag the muscle group furthest behind its weekly target.

    Only one, and only mid-week onwards: telling someone on Monday morning that
    their legs are at 0% is noise, not insight.
    """
    if not trained_this_week:
        return []

    behind = [
        ring
        for ring in rings
        if ring.weekly_target > 0 and ring.sets_this_week < ring.weekly_target * VOLUME_GAP_FRACTION
    ]
    if not behind:
        return []

    worst = min(behind, key=lambda r: r.sets_this_week / r.weekly_target)
    pct = round(worst.sets_this_week / worst.weekly_target * 100)

    return [
        Suggestion(
            id=f"volume-{worst.muscle_group}",
            kind="volume_gap",
            message=(
                f"{worst.muscle_group.capitalize()} is at {pct}% of your weekly target — "
                f"{worst.sets_this_week} of {worst.weekly_target} sets since Monday."
            ),
            evidence={
                "muscle_group": worst.muscle_group,
                "sets_this_week": worst.sets_this_week,
                "weekly_target": worst.weekly_target,
                "pct_of_target": pct,
            },
        )
    ]


def from_goal(
    *,
    progress_pct: float | None,
    projected_date: str | None,
    target_date: str | None,
    on_track: bool | None,
) -> list[Suggestion]:
    """Only speak when the projection actually disagrees with the target."""
    if projected_date is None or target_date is None or on_track is None:
        return []

    if on_track:
        message = (
            f"At your current rate you reach your goal around {projected_date}, "
            f"ahead of the {target_date} you set."
        )
    else:
        message = (
            f"At your current rate you reach your goal around {projected_date}, "
            f"later than the {target_date} you set."
        )

    return [
        Suggestion(
            id="goal-projection",
            kind="goal_projection",
            message=message,
            evidence={
                "projected_date": projected_date,
                "target_date": target_date,
                "progress_pct": round(progress_pct or 0.0, 1),
                "on_track": on_track,
            },
        )
    ]


def from_logging(*, logged_14: int, window_days: int = 14) -> list[Suggestion]:
    """Below a certain density, every other number here is guesswork."""
    if logged_14 >= LOGGING_NUDGE_THRESHOLD:
        return []

    return [
        Suggestion(
            id="logging",
            kind="logging_nudge",
            message=(
                f"You have logged {logged_14} of the last {window_days} days. Daily weight and "
                f"calories are what the maintenance estimate and the trend are built from."
            ),
            evidence={"logged_days": logged_14, "window_days": window_days},
        )
    ]


def assemble(*groups: list[Suggestion], limit: int = MAX_SUGGESTIONS) -> list[Suggestion]:
    """Rank by kind and keep the top few (spec §7.5).

    A stable sort means several plateaus keep the order plateau detection chose
    — heaviest lift first — rather than being reshuffled arbitrarily.
    """
    everything = [suggestion for group in groups for suggestion in group]
    everything.sort(key=lambda s: _priority(s.kind))
    return everything[:limit]
