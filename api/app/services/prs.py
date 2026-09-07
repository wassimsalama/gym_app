"""Personal records via estimated 1-rep max (spec §7.3).

Comparing raw top sets is useless across rep ranges — is 100 kg x 5 better than
110 kg x 3? Epley's estimate puts every set on one scale so they can be ranked:

    e1rm = weight * (1 + reps / 30)

Reps are capped at 12 *inside the formula only*. Past about a dozen reps the
estimate inflates nonsensically (a 20-rep set would "beat" a heavy triple), but
the real rep count is still what gets stored — the cap is a property of the
comparison, not of the data.

Pure functions over plain data, so none of this needs a database to test.
"""

from dataclasses import dataclass

#: Beyond this the linear estimate stops tracking reality; see module docstring.
EPLEY_REP_CAP = 12

#: Tolerance when comparing two e1RM estimates.
#:
#: The historical best is aggregated in SQL and the session's is computed here,
#: so the two travel through different arithmetic. Without a tolerance, a
#: last-bit difference on an identical lift reads as a record. A microgram of
#: slack is far below anything a barbell can express.
PR_EPSILON_KG = 1e-6


@dataclass(frozen=True)
class SetPerformance:
    """One logged set, reduced to what PR detection needs."""

    exercise_id: int
    weight_kg: float
    reps: int


@dataclass(frozen=True)
class PersonalRecord:
    exercise_id: int
    e1rm: float
    previous_e1rm: float


def epley_e1rm(weight_kg: float, reps: int) -> float:
    """Estimated one-rep max for a set. Reps are clamped to `EPLEY_REP_CAP`."""
    if weight_kg <= 0 or reps <= 0:
        return 0.0
    return weight_kg * (1 + min(reps, EPLEY_REP_CAP) / 30)


def best_e1rm_per_exercise(sets: list[SetPerformance]) -> dict[int, float]:
    """Top estimated 1RM for each exercise in a collection of sets."""
    best: dict[int, float] = {}
    for performance in sets:
        estimate = epley_e1rm(performance.weight_kg, performance.reps)
        if estimate > best.get(performance.exercise_id, 0.0):
            best[performance.exercise_id] = estimate
    return best


def detect(
    session_sets: list[SetPerformance],
    historical_best: dict[int, float],
) -> list[PersonalRecord]:
    """PRs set by this session.

    `historical_best` is the user's best e1RM per exercise *before* this
    session. An exercise absent from it has never been performed, and a first
    attempt is not a record — there is nothing it beat (spec §7.3). Ties are not
    records either: the comparison is strictly greater, within `PR_EPSILON_KG`.
    """
    records: list[PersonalRecord] = []

    for exercise_id, session_best in best_e1rm_per_exercise(session_sets).items():
        previous = historical_best.get(exercise_id)
        if previous is None:
            continue  # no baseline — first ever performance
        if session_best > previous + PR_EPSILON_KG:
            records.append(
                PersonalRecord(
                    exercise_id=exercise_id,
                    e1rm=session_best,
                    previous_e1rm=previous,
                )
            )

    # Biggest leap first, so the celebration leads with the best news.
    records.sort(key=lambda r: r.e1rm - r.previous_e1rm, reverse=True)
    return records
