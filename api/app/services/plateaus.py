"""Plateau detection, with cross-stream context (spec §7.4).

This is the product's whole argument. Any app can notice a lift has stopped
moving. The useful part is knowing *why*, and the answer usually lives in a
different data stream: strength stalling during a 400 kcal deficit is expected
physiology, not a training failure, and telling someone to add volume would be
actively bad advice.

So a plateau is never reported bare — it always carries the numbers that
explain it.
"""

from dataclasses import dataclass, field
from datetime import date

#: How many recent sessions define "stalled".
LOOKBACK_SESSIONS = 4

#: An exercise needs this much history before a flat patch means anything.
MIN_SESSIONS = 4

#: Spread across the lookback, as a fraction of the best. Under this the lift
#: has not meaningfully moved.
PLATEAU_SPREAD = 0.02

#: Daily deficit past which strength stalls are expected rather than surprising.
MEANINGFUL_DEFICIT_KCAL = 300

#: Fewer rest days than usual, past which recovery is the likelier cause.
REST_DAY_SHORTFALL = 2


@dataclass(frozen=True)
class ExerciseHistory:
    """Top-set e1RM per session for one exercise, oldest first."""

    exercise_id: int
    exercise_name: str
    session_dates: list[date]
    top_e1rms: list[float]


@dataclass(frozen=True)
class CalorieContext:
    mean_calories: float
    tdee_estimate: int

    @property
    def deficit(self) -> float:
        """Positive when eating under maintenance."""
        return self.tdee_estimate - self.mean_calories


@dataclass(frozen=True)
class RecoveryContext:
    rest_days_recent: int
    rest_days_typical: float

    @property
    def shortfall(self) -> float:
        return self.rest_days_typical - self.rest_days_recent


@dataclass(frozen=True)
class Plateau:
    exercise_id: int
    exercise_name: str
    sessions: int
    best_e1rm: float
    spread_pct: float
    #: Populated only when a stream actually explains the stall.
    calorie: CalorieContext | None = None
    recovery: RecoveryContext | None = None
    evidence: dict = field(default_factory=dict)


def is_plateaued(top_e1rms: list[float]) -> bool:
    """True when the last `LOOKBACK_SESSIONS` sit within `PLATEAU_SPREAD`."""
    if len(top_e1rms) < MIN_SESSIONS:
        return False

    window = top_e1rms[-LOOKBACK_SESSIONS:]
    best = max(window)
    if best <= 0:
        return False

    return (best - min(window)) / best <= PLATEAU_SPREAD


def detect(
    histories: list[ExerciseHistory],
    *,
    calorie: CalorieContext | None = None,
    recovery: RecoveryContext | None = None,
) -> list[Plateau]:
    """Stalled exercises, each carrying whatever explains it.

    Context is attached only when it is actually informative: a deficit under
    `MEANINGFUL_DEFICIT_KCAL` does not explain a stall, and saying so anyway
    would be the kind of confident noise §7.5 forbids.
    """
    plateaus: list[Plateau] = []

    for history in histories:
        if not is_plateaued(history.top_e1rms):
            continue

        window = history.top_e1rms[-LOOKBACK_SESSIONS:]
        best = max(window)
        spread_pct = (best - min(window)) / best * 100

        relevant_calorie = (
            calorie if calorie is not None and calorie.deficit > MEANINGFUL_DEFICIT_KCAL else None
        )
        relevant_recovery = (
            recovery if recovery is not None and recovery.shortfall >= REST_DAY_SHORTFALL else None
        )

        evidence: dict = {
            "sessions": LOOKBACK_SESSIONS,
            "best_e1rm_kg": round(best, 1),
            "spread_pct": round(spread_pct, 1),
        }
        if relevant_calorie is not None:
            evidence["mean_calories"] = round(relevant_calorie.mean_calories)
            evidence["tdee_estimate"] = relevant_calorie.tdee_estimate
            evidence["deficit_kcal"] = round(relevant_calorie.deficit)
        if relevant_recovery is not None:
            evidence["rest_days_recent"] = relevant_recovery.rest_days_recent
            evidence["rest_days_typical"] = round(relevant_recovery.rest_days_typical, 1)

        plateaus.append(
            Plateau(
                exercise_id=history.exercise_id,
                exercise_name=history.exercise_name,
                sessions=LOOKBACK_SESSIONS,
                best_e1rm=best,
                spread_pct=spread_pct,
                calorie=relevant_calorie,
                recovery=relevant_recovery,
                evidence=evidence,
            )
        )

    # Lead with the lift the user has most invested in.
    plateaus.sort(key=lambda p: p.best_e1rm, reverse=True)
    return plateaus


def describe(plateau: Plateau) -> str:
    """The sentence shown to the user, with its numbers inline.

    §7.5 requires the copy to cite its evidence — "you've plateaued" is a
    horoscope, "stalled 4 sessions while eating 400 kcal under maintenance" is
    something a person can act on.
    """
    head = f"{plateau.exercise_name} has not moved in {plateau.sessions} sessions"

    if plateau.calorie is not None:
        return (
            f"{head}. You are averaging {round(plateau.calorie.mean_calories)} kcal against an "
            f"estimated {plateau.calorie.tdee_estimate} maintenance — about "
            f"{round(plateau.calorie.deficit)} under. Strength stalls on a deficit are "
            f"expected; this is likely diet-related, not a training problem."
        )

    if plateau.recovery is not None:
        return (
            f"{head}. You have taken {plateau.recovery.rest_days_recent} rest days in the last "
            f"fortnight against your usual {plateau.recovery.rest_days_typical:.1f}. "
            f"Under-recovery is the likelier cause than programming."
        )

    return (
        f"{head}, within {plateau.spread_pct:.1f}% at {plateau.best_e1rm:.0f} kg estimated 1RM. "
        f"Intake and rest look normal, so this one is worth a programming change."
    )
