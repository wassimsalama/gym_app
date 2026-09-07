"""Queries backing the dashboard's engine inputs.

Kept out of the router so it stays a thin parse-authorize-delegate layer (§11),
and out of `services/` so the engine stays pure Python over plain data.
"""

from datetime import date, timedelta

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.models import DailyLog, Exercise, SetLog, WorkoutSession
from app.services.plateaus import CalorieContext, ExerciseHistory, RecoveryContext
from app.services.prs import EPLEY_REP_CAP
from app.services.recap import BestLift

#: How far back plateau detection looks for sessions.
PLATEAU_HISTORY_DAYS = 120

#: Baseline period for "how much do you normally rest" (§7.4).
REST_BASELINE_WEEKS = 8


def _e1rm_expr():
    """Matches `prs.epley_e1rm` exactly — cast first so numeric(6,2) does not
    quantise the result and make an identical lift compare unequal."""
    weight = cast(SetLog.weight_kg, Float)
    reps = cast(func.least(SetLog.reps, EPLEY_REP_CAP), Float)
    return weight * (1 + reps / 30.0)


def exercise_histories(db: Session, user_id, as_of: date) -> list[ExerciseHistory]:
    """Top-set e1RM per session, per exercise, oldest first."""
    rows = db.execute(
        select(
            Exercise.id,
            Exercise.name,
            WorkoutSession.session_date,
            func.max(_e1rm_expr()).label("top"),
        )
        .join(SetLog, SetLog.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.session_date >= as_of - timedelta(days=PLATEAU_HISTORY_DAYS),
            WorkoutSession.session_date <= as_of,
        )
        .group_by(Exercise.id, Exercise.name, WorkoutSession.session_date)
        .order_by(Exercise.id, WorkoutSession.session_date)
    ).all()

    grouped: dict[int, ExerciseHistory] = {}
    for exercise_id, name, session_date, top in rows:
        existing = grouped.get(exercise_id)
        if existing is None:
            grouped[exercise_id] = ExerciseHistory(
                exercise_id=exercise_id,
                exercise_name=name,
                session_dates=[session_date],
                top_e1rms=[float(top)],
            )
        else:
            existing.session_dates.append(session_date)
            existing.top_e1rms.append(float(top))

    return list(grouped.values())


def calorie_context(
    db: Session, user_id, as_of: date, tdee_estimate: int | None
) -> tuple[CalorieContext | None, float | None]:
    """Fortnight mean intake, and its comparison against maintenance."""
    mean = db.scalar(
        select(func.avg(DailyLog.calories)).where(
            DailyLog.user_id == user_id,
            DailyLog.calories.is_not(None),
            DailyLog.log_date >= as_of - timedelta(days=13),
            DailyLog.log_date <= as_of,
        )
    )
    if mean is None:
        return None, None

    mean_calories = float(mean)
    if tdee_estimate is None:
        return None, mean_calories

    return CalorieContext(mean_calories=mean_calories, tdee_estimate=tdee_estimate), mean_calories


def recovery_context(db: Session, user_id, as_of: date) -> RecoveryContext | None:
    """Rest days in the last fortnight against the user's own usual rate.

    "Usual" is their trailing eight weeks, not a population average — someone
    who trains six days a week is not under-recovered for doing so, but is if
    they suddenly stop resting at all.
    """
    baseline_days = REST_BASELINE_WEEKS * 7
    baseline_start = as_of - timedelta(days=baseline_days - 1)

    def trained_days(since: date) -> int:
        flagged = set(
            db.scalars(
                select(DailyLog.log_date).where(
                    DailyLog.user_id == user_id,
                    DailyLog.trained.is_(True),
                    DailyLog.log_date >= since,
                    DailyLog.log_date <= as_of,
                )
            )
        )
        sessions = set(
            db.scalars(
                select(WorkoutSession.session_date).where(
                    WorkoutSession.user_id == user_id,
                    WorkoutSession.session_date >= since,
                    WorkoutSession.session_date <= as_of,
                )
            )
        )
        return len(flagged | sessions)

    recent_rest = 14 - trained_days(as_of - timedelta(days=13))

    baseline_trained = trained_days(baseline_start)
    if baseline_trained == 0:
        # No training history to compare against; saying anything would be guessing.
        return None

    typical_rest = (baseline_days - baseline_trained) / baseline_days * 14

    return RecoveryContext(rest_days_recent=recent_rest, rest_days_typical=typical_rest)


def week_best_lift(db: Session, user_id, start: date, end: date) -> BestLift | None:
    """Heaviest estimated 1RM of the week, and what it stood against."""
    row = db.execute(
        select(Exercise.id, Exercise.name, func.max(_e1rm_expr()).label("best"))
        .join(SetLog, SetLog.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.session_date >= start,
            WorkoutSession.session_date <= end,
        )
        .group_by(Exercise.id, Exercise.name)
        .order_by(func.max(_e1rm_expr()).desc())
        .limit(1)
    ).first()

    if row is None:
        return None

    exercise_id, name, best = row
    previous = db.scalar(
        select(func.max(_e1rm_expr()))
        .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
        .where(
            WorkoutSession.user_id == user_id,
            SetLog.exercise_id == exercise_id,
            WorkoutSession.session_date < start,
        )
    )

    return BestLift(
        exercise_id=exercise_id,
        exercise_name=name,
        e1rm=round(float(best), 2),
        previous_best=round(float(previous), 2) if previous is not None else None,
    )


def week_totals(db: Session, user_id, start: date, end: date):
    """Session dates and every (weight, reps) pair inside the week."""
    session_dates = list(
        db.scalars(
            select(WorkoutSession.session_date).where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.session_date >= start,
                WorkoutSession.session_date <= end,
            )
        )
    )
    set_volumes = [
        (float(weight), reps)
        for weight, reps in db.execute(
            select(SetLog.weight_kg, SetLog.reps)
            .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.session_date >= start,
                WorkoutSession.session_date <= end,
            )
        ).all()
    ]
    return session_dates, set_volumes
