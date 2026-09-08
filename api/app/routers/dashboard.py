from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.auth import DbSession
from app.core.limits import ReadUser
from app.models import Goal, UserActivity
from app.routers import _dashboard_data as data
from app.schemas.dashboard import (
    BestLift,
    Dashboard,
    GoalBlock,
    Recap,
    StepsBlock,
    Streaks,
    Suggestion,
    TdeeBlock,
    VolumeRing,
    WeightBlock,
    WeightSeriesPoint,
)
from app.services import plateaus, projection, recap, steps, streaks, suggestions, tdee
from app.services.smoothing import smooth_series

router = APIRouter(tags=["dashboard"])

#: How far back the series reaches. The weight tab narrows this client-side.
MAX_SERIES_DAYS = 365


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

    `date` comes from the client because only the device knows what day it is
    where the user is standing — §6 forbids the server deriving it from UTC, and
    streaks, Monday-anchored volume weeks and the recap all need a calendar day.

    The data is fetched in a handful of round trips up front and every service
    derives its answer from that in memory. Asking per-service was 23 trips,
    which is invisible on a local socket and fatal across a continent.
    """
    # At most one write per user per day, however often they look.
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

    recap_start, recap_end = recap.last_completed_week(today)
    loaded = data.load(
        db,
        user.id,
        today=today,
        series_days=MAX_SERIES_DAYS,
        recap_week_start=recap_start,
    )

    # --- weight ------------------------------------------------------------
    points = smooth_series(loaded.weights())
    current_smoothed = points[-1].smoothed_kg if points else None
    delta = (
        current_smoothed - float(goal.start_weight_kg)
        if current_smoothed is not None and goal is not None
        else None
    )

    # --- goal --------------------------------------------------------------
    # Steps over the trailing week. Days with no count are skipped rather than
    # read as zero — see services/steps.py for why that distinction matters here.
    step_window = [
        row.steps
        for row in loaded.logs
        if (today - row.log_date).days < steps.WINDOW_DAYS and row.log_date <= today
    ]
    step_summary = steps.summarise(
        step_window,
        today_value=next((row.steps for row in loaded.logs if row.log_date == today), None),
    )

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
    counted = streaks.count_streaks(
        logged_dates=loaded.logged_dates(since=streak_start, until=today),
        trained_dates=loaded.trained_dates(since=streak_start, until=today),
        as_of=today,
    )

    # --- volume ------------------------------------------------------------
    monday = streaks.week_start(today)
    sets_by_group = loaded.sets_by_muscle_group(since=monday, until=today)
    rings = streaks.volume_rings(sets_by_group=sets_by_group)

    # --- tdee --------------------------------------------------------------
    estimate = tdee.estimate(
        points,
        loaded.calories_by_date(since=today - timedelta(days=tdee.WINDOW_DAYS - 1), until=today),
        as_of=today,
    )

    # --- suggestions -------------------------------------------------------
    fortnight = loaded.calories_by_date(since=today - timedelta(days=13), until=today)
    mean_calories = sum(fortnight.values()) / len(fortnight) if fortnight else None

    calorie_ctx = (
        plateaus.CalorieContext(mean_calories=mean_calories, tdee_estimate=estimate.estimate_kcal)
        if mean_calories is not None and estimate.reliable and estimate.estimate_kcal
        else None
    )

    assembled = suggestions.assemble(
        suggestions.from_plateaus(
            plateaus.detect(
                loaded.exercise_histories(),
                calorie=calorie_ctx,
                recovery=_recovery(loaded, today),
            )
        ),
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
        steps=StepsBlock(
            today=step_summary.today,
            average=step_summary.average,
            days_logged=step_summary.days_logged,
            reliable=step_summary.reliable,
        ),
        volume=[
            VolumeRing(
                muscle_group=ring.muscle_group,
                sets_this_week=ring.sets_this_week,
                weekly_target=ring.weekly_target,
            )
            for ring in rings
        ],
        prs_recent=_recent_prs(loaded, today),
        suggestions=[
            Suggestion(id=s.id, kind=s.kind, message=s.message, evidence=s.evidence)
            for s in assembled
        ],
        recap=_build_recap(loaded, points, today, recap_start, recap_end),
    )


def _recovery(loaded: data.DashboardData, today: date) -> plateaus.RecoveryContext | None:
    """Rest days lately against the user's own usual rate (§7.4).

    Compared against their own trailing habit, not a population average: someone
    who trains six days a week is not under-recovered for doing so, but is if
    they suddenly stop resting at all.
    """
    baseline_days = data.REST_BASELINE_WEEKS * 7
    baseline_trained = loaded.trained_dates(
        since=today - timedelta(days=baseline_days - 1), until=today
    )
    if not baseline_trained:
        return None

    recent_trained = loaded.trained_dates(since=today - timedelta(days=13), until=today)

    return plateaus.RecoveryContext(
        rest_days_recent=14 - len(recent_trained),
        rest_days_typical=(baseline_days - len(baseline_trained)) / baseline_days * 14,
    )


def _recent_prs(loaded: data.DashboardData, today: date) -> list[dict]:
    """Lifts in the last week that beat everything before them.

    Recomputed rather than stored: §5 forbids persisting derived values, and a
    cached `is_pr` goes stale the moment an old session is edited.
    """
    since = today - timedelta(days=data.PR_WINDOW_DAYS - 1)

    records = []
    for exercise_id, (name, best, achieved_on) in loaded.best_e1rm_between(
        since=since, until=today
    ).items():
        prior = loaded.pr_baseline.get(exercise_id)
        if prior is not None and best > prior:
            records.append(
                {
                    "exercise_id": exercise_id,
                    "exercise_name": name,
                    "e1rm": round(best, 2),
                    "previous_e1rm": round(prior, 2),
                    "achieved_on": achieved_on.isoformat(),
                }
            )

    records.sort(key=lambda r: r["e1rm"] - r["previous_e1rm"], reverse=True)
    return records


def _build_recap(
    loaded: data.DashboardData, points: list, today: date, start: date, end: date
) -> Recap | None:
    """The last completed Mon–Sun week (spec §7.7)."""
    logged = loaded.logged_dates(since=start, until=end)
    session_dates = sorted(d for d in loaded.session_dates if start <= d <= end)

    if not logged and not session_dates:
        return None

    week_sets = [row for row in loaded.sets if start <= row.session_date <= end]
    best_lift = None
    week_best = loaded.best_e1rm_between(since=start, until=end)
    if week_best:
        exercise_id, (name, e1rm, _) = max(week_best.items(), key=lambda item: item[1][1])
        best_lift = recap.BestLift(
            exercise_id=exercise_id,
            exercise_name=name,
            e1rm=round(e1rm, 2),
            previous_best=(
                round(loaded.recap_baseline[exercise_id], 2)
                if exercise_id in loaded.recap_baseline
                else None
            ),
        )

    in_week = [p for p in points if start <= p.date <= end]
    built = recap.build(
        as_of=today,
        session_dates=session_dates,
        set_volumes=[(row.weight_kg, row.reps) for row in week_sets],
        logged_dates=logged,
        trained_dates=loaded.trained_dates(since=start, until=end),
        smoothed_start=in_week[0].smoothed_kg if in_week else None,
        smoothed_end=in_week[-1].smoothed_kg if in_week else None,
        best_lift=best_lift,
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
