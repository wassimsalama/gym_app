from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.auth import DbSession
from app.core.limits import ReadUser
from app.models import DailyLog, Exercise, Goal, SetLog, UserActivity, WorkoutSession
from app.routers import _dashboard_data as data
from app.schemas.dashboard import (
    BestLift,
    Dashboard,
    GoalBlock,
    Recap,
    Streaks,
    Suggestion,
    TdeeBlock,
    VolumeRing,
    WeightBlock,
    WeightSeriesPoint,
)
from app.services import plateaus, projection, recap, streaks, suggestions, tdee
from app.services.prs import EPLEY_REP_CAP
from app.services.smoothing import smooth_series

router = APIRouter(tags=["dashboard"])

#: How far back the series reaches. The weight tab narrows this client-side, so
#: the window only needs to be the widest span anyone can ask for. A year of
#: daily points is roughly 20 KB, well inside §12's one-second budget.
MAX_SERIES_DAYS = 365

#: Recent PRs shown on the home tab (spec §6).
PR_WINDOW_DAYS = 7


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(
    user: ReadUser,
    db: DbSession,
    today: date = Query(
        alias="date",
        description="The client's local date. The server never derives it (spec §6).",
    ),
) -> Dashboard:
    """Everything the home tab renders, in one request (spec §6).

    `date` is supplied by the client because only the device knows what day it
    is where the user is standing — §6 forbids the server deriving "today" from
    UTC, and streaks, Monday-anchored volume weeks and the recap all need a real
    calendar day. It matches how `PUT /daily-logs/{date}` already works.
    """
    # The home tab makes exactly one request per app open, so this is the
    # natural place to note that the user was here. ON CONFLICT DO NOTHING makes
    # it at most one write per user per day, whatever else they do.
    db.execute(
        pg_insert(UserActivity)
        .values(user_id=user.id, active_on=today)
        .on_conflict_do_nothing(index_elements=["user_id", "active_on"])
    )
    db.commit()

    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .limit(1)
    )

    # --- weight ------------------------------------------------------------
    window_start = today - timedelta(days=MAX_SERIES_DAYS - 1)
    observations = db.execute(
        select(DailyLog.log_date, DailyLog.weight_kg)
        .where(
            DailyLog.user_id == user.id,
            DailyLog.weight_kg.is_not(None),
            DailyLog.log_date >= window_start,
            DailyLog.log_date <= today,
        )
        .order_by(DailyLog.log_date)
    ).all()
    points = smooth_series([(day, float(kg)) for day, kg in observations])

    current_smoothed = points[-1].smoothed_kg if points else None
    delta = (
        current_smoothed - float(goal.start_weight_kg)
        if current_smoothed is not None and goal is not None
        else None
    )

    # --- goal --------------------------------------------------------------
    goal_block = None
    if goal is not None:
        evaluated = projection.evaluate(
            start_kg=float(goal.start_weight_kg),
            goal_kg=float(goal.goal_weight_kg),
            points=points,
            as_of=points[-1].date if points else goal.start_date,
            target_date=goal.target_date,
        )
        goal_block = GoalBlock(
            progress_pct=evaluated.progress_pct,
            projected_date=evaluated.projected_date,
            on_track=evaluated.on_track,
            start_weight_kg=float(goal.start_weight_kg),
            goal_weight_kg=float(goal.goal_weight_kg),
        )

    # --- streaks -----------------------------------------------------------
    streak_start = today - timedelta(days=streaks.STREAK_WINDOW_DAYS - 1)
    logged_dates = set(
        db.scalars(
            select(DailyLog.log_date).where(
                DailyLog.user_id == user.id,
                DailyLog.log_date >= streak_start,
                DailyLog.log_date <= today,
            )
        )
    )
    trained_dates = set(
        db.scalars(
            select(DailyLog.log_date).where(
                DailyLog.user_id == user.id,
                DailyLog.trained.is_(True),
                DailyLog.log_date >= streak_start,
                DailyLog.log_date <= today,
            )
        )
    )
    # Spec §7.6: a logged session counts as training whether or not the flag
    # was also set.
    trained_dates |= set(
        db.scalars(
            select(WorkoutSession.session_date).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.session_date >= streak_start,
                WorkoutSession.session_date <= today,
            )
        )
    )
    counted = streaks.count_streaks(
        logged_dates=logged_dates, trained_dates=trained_dates, as_of=today
    )

    # --- volume rings ------------------------------------------------------
    monday = streaks.week_start(today)
    sets_by_group = dict(
        db.execute(
            select(Exercise.muscle_group, func.count(SetLog.id))
            .join(SetLog, SetLog.exercise_id == Exercise.id)
            .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
            .where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.session_date >= monday,
                WorkoutSession.session_date <= today,
            )
            .group_by(Exercise.muscle_group)
        ).all()
    )

    # --- tdee --------------------------------------------------------------
    calorie_rows = db.execute(
        select(DailyLog.log_date, DailyLog.calories).where(
            DailyLog.user_id == user.id,
            DailyLog.calories.is_not(None),
            DailyLog.log_date >= today - timedelta(days=tdee.WINDOW_DAYS - 1),
            DailyLog.log_date <= today,
        )
    ).all()
    estimate = tdee.estimate(points, dict(calorie_rows), as_of=today)

    rings = streaks.volume_rings(sets_by_group=sets_by_group)

    # --- suggestions -------------------------------------------------------
    calorie_ctx, mean_calories = data.calorie_context(
        db, user.id, today, estimate.estimate_kcal if estimate.reliable else None
    )
    found_plateaus = plateaus.detect(
        data.exercise_histories(db, user.id, today),
        calorie=calorie_ctx,
        recovery=data.recovery_context(db, user.id, today),
    )
    assembled = suggestions.assemble(
        suggestions.from_plateaus(found_plateaus),
        suggestions.from_tdee(estimate, mean_calories),
        suggestions.from_volume(rings, trained_this_week=bool(sets_by_group)),
        suggestions.from_goal(
            progress_pct=goal_block.progress_pct if goal_block else None,
            projected_date=(
                goal_block.projected_date.isoformat()
                if goal_block and goal_block.projected_date
                else None
            ),
            target_date=goal.target_date.isoformat() if goal and goal.target_date else None,
            on_track=goal_block.on_track if goal_block else None,
        ),
        suggestions.from_logging(logged_14=counted.logged_14),
    )

    return Dashboard(
        streaks=Streaks(logged_14=counted.logged_14, trained_14=counted.trained_14),
        weight=WeightBlock(
            current_smoothed_kg=current_smoothed,
            delta_since_start_kg=delta,
            series=[
                WeightSeriesPoint(date=p.date, raw_kg=p.raw_kg, smoothed_kg=p.smoothed_kg)
                for p in points
            ],
        ),
        goal=goal_block,
        tdee=TdeeBlock(
            estimate_kcal=estimate.estimate_kcal,
            days_of_data=estimate.days_of_data,
            reliable=estimate.reliable,
        ),
        volume=[
            VolumeRing(
                muscle_group=ring.muscle_group,
                sets_this_week=ring.sets_this_week,
                weekly_target=ring.weekly_target,
            )
            for ring in rings
        ],
        prs_recent=_recent_prs(db, user.id, today),
        suggestions=[
            Suggestion(id=s.id, kind=s.kind, message=s.message, evidence=s.evidence)
            for s in assembled
        ],
        recap=_build_recap(db, user.id, today, points),
    )


def _build_recap(db, user_id, today: date, points: list) -> Recap | None:
    """The last completed Mon–Sun week (spec §7.7).

    Returned whenever there is a finished week with anything in it, rather than
    only on Sundays — a recap the user cannot look back at on Tuesday is a
    recap they will mostly never see.
    """
    start, end = recap.last_completed_week(today)

    session_dates, set_volumes = data.week_totals(db, user_id, start, end)
    logged = set(
        db.scalars(
            select(DailyLog.log_date).where(
                DailyLog.user_id == user_id,
                DailyLog.log_date >= start,
                DailyLog.log_date <= end,
            )
        )
    )
    trained = set(
        db.scalars(
            select(DailyLog.log_date).where(
                DailyLog.user_id == user_id,
                DailyLog.trained.is_(True),
                DailyLog.log_date >= start,
                DailyLog.log_date <= end,
            )
        )
    ) | set(session_dates)

    if not logged and not session_dates:
        return None

    in_week = [p for p in points if start <= p.date <= end]
    built = recap.build(
        as_of=today,
        session_dates=session_dates,
        set_volumes=set_volumes,
        logged_dates=logged,
        trained_dates=trained,
        smoothed_start=in_week[0].smoothed_kg if in_week else None,
        smoothed_end=in_week[-1].smoothed_kg if in_week else None,
        best_lift=data.week_best_lift(db, user_id, start, end),
    )

    return Recap(
        week_start=built.week_start,
        week_end=built.week_end,
        sessions=built.sessions,
        total_sets=built.total_sets,
        total_volume_kg=round(built.total_volume_kg, 1),
        weight_delta_kg=(
            round(built.weight_delta_kg, 2) if built.weight_delta_kg is not None else None
        ),
        days_trained=built.days_trained,
        days_logged=built.days_logged,
        best_lift=(
            BestLift(
                exercise_id=built.best_lift.exercise_id,
                exercise_name=built.best_lift.exercise_name,
                e1rm=built.best_lift.e1rm,
                previous_best=built.best_lift.previous_best,
                was_a_record=built.best_lift.was_a_record,
            )
            if built.best_lift
            else None
        ),
    )


def _recent_prs(db, user_id, today: date) -> list[dict]:
    """Best e1RM per exercise in the last week, where it beat everything prior.

    Recomputed rather than stored: §5 forbids persisting derived values, and a
    cached `is_pr` would go stale the moment an old session was edited.
    """
    since = today - timedelta(days=PR_WINDOW_DAYS - 1)

    e1rm = SetLog.weight_kg * (1 + func.least(SetLog.reps, EPLEY_REP_CAP) / 30.0)
    recent = db.execute(
        select(
            Exercise.id,
            Exercise.name,
            func.max(e1rm).label("best"),
            func.max(WorkoutSession.session_date).label("achieved_on"),
        )
        .join(SetLog, SetLog.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.session_date >= since,
            WorkoutSession.session_date <= today,
        )
        .group_by(Exercise.id, Exercise.name)
    ).all()

    records = []
    for exercise_id, name, best, achieved_on in recent:
        prior = db.scalar(
            select(func.max(e1rm))
            .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
            .where(
                WorkoutSession.user_id == user_id,
                SetLog.exercise_id == exercise_id,
                WorkoutSession.session_date < since,
            )
        )
        if prior is not None and float(best) > float(prior):
            records.append(
                {
                    "exercise_id": exercise_id,
                    "exercise_name": name,
                    "e1rm": round(float(best), 2),
                    "previous_e1rm": round(float(prior), 2),
                    "achieved_on": achieved_on.isoformat(),
                }
            )

    records.sort(key=lambda r: r["e1rm"] - r["previous_e1rm"], reverse=True)
    return records
