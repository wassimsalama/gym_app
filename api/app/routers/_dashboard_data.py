"""Fetching the dashboard's data in as few round trips as possible.

The endpoint needs weights, calories, sessions, sets, muscle groups, streaks,
volume, plateaus, PRs and a recap. Asking the database separately for each was
23 round trips, which is fine on a socket in the same rack and ruinous across a
continent — latency multiplies by the number of trips, not the amount of data.

So the shape here is: two windowed reads plus two small aggregates, and every
service derives what it needs from those in Python. The row counts are tiny —
a year of daily logs is 365 rows — so moving the work out of SQL costs nothing
and saves nineteen network round trips.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.models import DailyLog, Exercise, SetLog, WorkoutSession
from app.services.plateaus import ExerciseHistory
from app.services.prs import EPLEY_REP_CAP

#: How far back plateau detection looks for sessions.
PLATEAU_HISTORY_DAYS = 120

#: Baseline period for "how much do you normally rest" (§7.4).
REST_BASELINE_WEEKS = 8

#: Recent PRs shown on the home tab (spec §6).
PR_WINDOW_DAYS = 7


@dataclass(frozen=True)
class LogRow:
    log_date: date
    weight_kg: float | None
    calories: int | None
    trained: bool | None


@dataclass(frozen=True)
class SetRow:
    session_date: date
    exercise_id: int
    exercise_name: str
    muscle_group: str
    weight_kg: float
    reps: int

    @property
    def e1rm(self) -> float:
        """Matches `prs.epley_e1rm` exactly — the two must not drift apart."""
        return self.weight_kg * (1 + min(self.reps, EPLEY_REP_CAP) / 30)

    @property
    def volume(self) -> float:
        return self.weight_kg * self.reps


@dataclass
class DashboardData:
    """Everything one dashboard render needs, fetched up front."""

    logs: list[LogRow] = field(default_factory=list)
    sets: list[SetRow] = field(default_factory=list)
    session_dates: set[date] = field(default_factory=set)
    #: Best e1RM per exercise strictly before the recent-PR window.
    pr_baseline: dict[int, float] = field(default_factory=dict)
    #: Best e1RM per exercise strictly before the recap week.
    recap_baseline: dict[int, float] = field(default_factory=dict)

    # --- derived views, all in memory ------------------------------------

    def weights(self) -> list[tuple[date, float]]:
        return [(row.log_date, row.weight_kg) for row in self.logs if row.weight_kg is not None]

    def calories_by_date(self, *, since: date, until: date) -> dict[date, int]:
        return {
            row.log_date: row.calories
            for row in self.logs
            if row.calories is not None and since <= row.log_date <= until
        }

    def logged_dates(self, *, since: date, until: date) -> set[date]:
        return {row.log_date for row in self.logs if since <= row.log_date <= until}

    def trained_dates(self, *, since: date, until: date) -> set[date]:
        """A logged session counts as training whether or not the flag is set (§7.6)."""
        flagged = {
            row.log_date for row in self.logs if row.trained and since <= row.log_date <= until
        }
        return flagged | {d for d in self.session_dates if since <= d <= until}

    def sets_by_muscle_group(self, *, since: date, until: date) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for row in self.sets:
            if since <= row.session_date <= until:
                counts[row.muscle_group] += 1
        return dict(counts)

    def exercise_histories(self) -> list[ExerciseHistory]:
        """Top-set e1RM per session, per exercise, oldest first."""
        tops: dict[int, dict[date, float]] = defaultdict(dict)
        names: dict[int, str] = {}

        for row in self.sets:
            names[row.exercise_id] = row.exercise_name
            by_day = tops[row.exercise_id]
            if row.e1rm > by_day.get(row.session_date, 0.0):
                by_day[row.session_date] = row.e1rm

        return [
            ExerciseHistory(
                exercise_id=exercise_id,
                exercise_name=names[exercise_id],
                session_dates=sorted(by_day),
                top_e1rms=[by_day[day] for day in sorted(by_day)],
            )
            for exercise_id, by_day in tops.items()
        ]

    def best_e1rm_between(self, *, since: date, until: date) -> dict[int, tuple[str, float, date]]:
        """Best e1RM per exercise in a span, with its name and the day it happened."""
        best: dict[int, tuple[str, float, date]] = {}
        for row in self.sets:
            if not (since <= row.session_date <= until):
                continue
            current = best.get(row.exercise_id)
            if current is None or row.e1rm > current[1]:
                best[row.exercise_id] = (row.exercise_name, row.e1rm, row.session_date)
        return best


def _e1rm_expr():
    """Cast before arithmetic so numeric(6,2) does not quantise the result."""
    weight = cast(SetLog.weight_kg, Float)
    reps = cast(func.least(SetLog.reps, EPLEY_REP_CAP), Float)
    return weight * (1 + reps / 30.0)


def _baseline_before(db: Session, user_id, cutoff: date) -> dict[int, float]:
    """Best e1RM per exercise strictly before a date, across all history."""
    rows = db.execute(
        select(SetLog.exercise_id, func.max(_e1rm_expr()))
        .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
        .where(WorkoutSession.user_id == user_id, WorkoutSession.session_date < cutoff)
        .group_by(SetLog.exercise_id)
    ).all()
    return {exercise_id: float(best) for exercise_id, best in rows}


def load(
    db: Session, user_id, *, today: date, series_days: int, recap_week_start: date
) -> DashboardData:
    """Four round trips, covering every service the dashboard calls."""
    log_window = today - timedelta(days=series_days - 1)
    # Wide enough for plateaus, the rest baseline, volume and the recap.
    session_window = min(
        today - timedelta(days=PLATEAU_HISTORY_DAYS),
        today - timedelta(days=REST_BASELINE_WEEKS * 7 - 1),
        recap_week_start,
    )

    logs = [
        LogRow(
            log_date=row.log_date,
            weight_kg=float(row.weight_kg) if row.weight_kg is not None else None,
            calories=row.calories,
            trained=row.trained,
        )
        for row in db.execute(
            select(DailyLog.log_date, DailyLog.weight_kg, DailyLog.calories, DailyLog.trained)
            .where(
                DailyLog.user_id == user_id,
                DailyLog.log_date >= log_window,
                DailyLog.log_date <= today,
            )
            .order_by(DailyLog.log_date)
        ).all()
    ]

    set_rows = db.execute(
        select(
            WorkoutSession.session_date,
            Exercise.id,
            Exercise.name,
            Exercise.muscle_group,
            SetLog.weight_kg,
            SetLog.reps,
        )
        .join(SetLog, SetLog.session_id == WorkoutSession.id)
        .join(Exercise, Exercise.id == SetLog.exercise_id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.session_date >= session_window,
            WorkoutSession.session_date <= today,
        )
        .order_by(WorkoutSession.session_date)
    ).all()

    sets = [
        SetRow(
            session_date=row[0],
            exercise_id=row[1],
            exercise_name=row[2],
            muscle_group=row[3],
            weight_kg=float(row[4]),
            reps=row[5],
        )
        for row in set_rows
    ]

    # Session dates come from the sets query for sessions that have any, plus a
    # cheap scan for quick-logged sessions which have none at all.
    session_dates = set(
        db.scalars(
            select(WorkoutSession.session_date).where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.session_date >= session_window,
                WorkoutSession.session_date <= today,
            )
        )
    )

    return DashboardData(
        logs=logs,
        sets=sets,
        session_dates=session_dates,
        pr_baseline=_baseline_before(db, user_id, today - timedelta(days=PR_WINDOW_DAYS - 1)),
        recap_baseline=_baseline_before(db, user_id, recap_week_start),
    )
