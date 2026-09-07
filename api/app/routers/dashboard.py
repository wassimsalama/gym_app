from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import select

from app.core.auth import CurrentUser, DbSession
from app.models import DailyLog, Goal
from app.schemas.dashboard import (
    Dashboard,
    GoalBlock,
    Streaks,
    TdeeBlock,
    WeightBlock,
    WeightSeriesPoint,
)
from app.services import projection
from app.services.smoothing import smooth_series

router = APIRouter(tags=["dashboard"])

#: How far back the series reaches. The weight tab lets the user narrow this to
#: 2 weeks / 1 month / 3 months client-side, so the window only needs to be the
#: widest span anyone can ask for — its "All" option means all of this.
#: A year of daily points is roughly 20 KB, well inside §12's one-second budget.
MAX_SERIES_DAYS = 365


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(user: CurrentUser, db: DbSession) -> Dashboard:
    """Everything the home tab renders, in one request (spec §6).

    Phase 1 fills in `weight` and `goal` for real. `streaks`, `volume`,
    `prs_recent`, `suggestions`, `tdee` and `recap` are shaped but empty until
    Phases 2–3 — the contract is stable, only the content grows.

    Note the absence of a "today": every window here is anchored to the user's
    most recent observation rather than to a server clock, because §6 forbids
    the server deciding what today is. Phases 2–3 need a real calendar today
    for streaks and Monday-anchored volume weeks — see DECISIONS.md.
    """
    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .limit(1)
    )

    latest_date = db.scalar(
        select(DailyLog.log_date)
        .where(DailyLog.user_id == user.id, DailyLog.weight_kg.is_not(None))
        .order_by(DailyLog.log_date.desc())
        .limit(1)
    )

    points: list = []
    if latest_date is not None:
        # Everything on record, bounded at a year. Backfilled history counts:
        # the user logged it precisely so it would show up.
        window_start = latest_date - timedelta(days=MAX_SERIES_DAYS - 1)
        if goal is not None:
            # Never start after the goal did, or "delta since start" and the
            # chart would disagree about where the journey began.
            window_start = min(window_start, goal.start_date)
            window_start = max(window_start, latest_date - timedelta(days=MAX_SERIES_DAYS - 1))

        observations = db.execute(
            select(DailyLog.log_date, DailyLog.weight_kg)
            .where(
                DailyLog.user_id == user.id,
                DailyLog.weight_kg.is_not(None),
                DailyLog.log_date >= window_start,
                DailyLog.log_date <= latest_date,
            )
            .order_by(DailyLog.log_date)
        ).all()
        points = smooth_series([(day, float(kg)) for day, kg in observations])

    current_smoothed = points[-1].smoothed_kg if points else None

    delta = None
    if current_smoothed is not None and goal is not None:
        delta = current_smoothed - float(goal.start_weight_kg)

    goal_block = None
    if goal is not None:
        evaluated = projection.evaluate(
            start_kg=float(goal.start_weight_kg),
            goal_kg=float(goal.goal_weight_kg),
            points=points,
            as_of=latest_date or goal.start_date,
            target_date=goal.target_date,
        )
        goal_block = GoalBlock(
            progress_pct=evaluated.progress_pct,
            projected_date=evaluated.projected_date,
            on_track=evaluated.on_track,
        )

    return Dashboard(
        streaks=Streaks(logged_14=0, trained_14=0),
        weight=WeightBlock(
            current_smoothed_kg=current_smoothed,
            delta_since_start_kg=delta,
            series=[
                WeightSeriesPoint(date=p.date, raw_kg=p.raw_kg, smoothed_kg=p.smoothed_kg)
                for p in points
            ],
        ),
        goal=goal_block,
        tdee=TdeeBlock(estimate_kcal=None, days_of_data=0, reliable=False),
        volume=[],
        prs_recent=[],
        suggestions=[],
        recap=None,
    )
