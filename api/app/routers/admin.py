from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import distinct, func, select

from app.core.auth import CurrentUser, DbSession
from app.core.config import get_settings
from app.models import DailyLog, Photo, Profile, UserActivity, WorkoutSession
from app.services import metrics

router = APIRouter(prefix="/admin", tags=["admin"])

#: How many weekly cohorts to report.
COHORT_WEEKS = 6


class CohortOut(BaseModel):
    week_start: date
    signed_up: int
    returned_week_1: int
    #: Null while the cohort's return window is still running — not zero.
    retention_pct: float | None
    complete: bool


class Metrics(BaseModel):
    as_of: date
    total_users: int
    signups_last_7: int
    signups_last_30: int
    active_1: int
    active_7: int
    active_30: int
    stickiness_pct: float
    users_who_logged_weight: int
    users_who_logged_macros: int
    users_who_logged_a_workout: int
    users_who_added_a_photo: int
    total_weight_logs: int
    total_sessions: int
    total_sets: int
    total_photos: int
    cohorts: list[CohortOut]


@router.get("/metrics", response_model=Metrics)
def get_metrics(
    user: CurrentUser,
    db: DbSession,
    today: date = Query(alias="date", description="The caller's local date (§6)."),
) -> Metrics:
    """Product metrics, for the owner only.

    Everything here is aggregate. There is no endpoint that returns one named
    person's data, deliberately: the question being answered is "is this being
    used", not "what is Dave doing".
    """
    admins = get_settings().admins
    if str(user.id) not in admins:
        # Say nothing about the endpoint existing.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    activity = _activity_by_day(db, since=today - timedelta(days=120), until=today)
    signups = _signups_by_day(db)

    active_1 = metrics.active_in_window(activity, as_of=today, days=1)
    active_30 = metrics.active_in_window(activity, as_of=today, days=30)

    first_cohort = _week_start(today) - timedelta(weeks=COHORT_WEEKS)
    cohorts = [
        metrics.retention(
            signups, activity, week_start=first_cohort + timedelta(weeks=i), as_of=today
        )
        for i in range(COHORT_WEEKS)
    ]

    return Metrics(
        as_of=today,
        total_users=db.scalar(select(func.count()).select_from(Profile)) or 0,
        signups_last_7=_signups_since(db, today - timedelta(days=6)),
        signups_last_30=_signups_since(db, today - timedelta(days=29)),
        active_1=active_1,
        active_7=metrics.active_in_window(activity, as_of=today, days=7),
        active_30=active_30,
        stickiness_pct=metrics.stickiness(active_1, active_30),
        users_who_logged_weight=_distinct_users(db, DailyLog, DailyLog.weight_kg.is_not(None)),
        users_who_logged_macros=_distinct_users(db, DailyLog, DailyLog.calories.is_not(None)),
        users_who_logged_a_workout=_distinct_users(db, WorkoutSession),
        users_who_added_a_photo=_distinct_users(db, Photo),
        total_weight_logs=db.scalar(
            select(func.count()).select_from(DailyLog).where(DailyLog.weight_kg.is_not(None))
        )
        or 0,
        total_sessions=db.scalar(select(func.count()).select_from(WorkoutSession)) or 0,
        total_sets=db.scalar(
            select(func.count()).select_from(
                select(WorkoutSession.id)
                .join(
                    WorkoutSession.sets.property.mapper.class_,
                    WorkoutSession.id == WorkoutSession.sets.property.mapper.class_.session_id,
                )
                .subquery()
            )
        )
        or 0,
        total_photos=db.scalar(select(func.count()).select_from(Photo)) or 0,
        cohorts=[
            CohortOut(
                week_start=c.week_start,
                signed_up=c.signed_up,
                returned_week_1=c.returned_week_1,
                retention_pct=None if c.retention_pct is None else round(c.retention_pct, 1),
                complete=c.complete,
            )
            for c in cohorts
        ],
    )


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _activity_by_day(db, *, since: date, until: date) -> dict[date, set]:
    rows = db.execute(
        select(UserActivity.active_on, UserActivity.user_id).where(
            UserActivity.active_on >= since, UserActivity.active_on <= until
        )
    ).all()

    grouped: dict[date, set] = {}
    for day, user_id in rows:
        grouped.setdefault(day, set()).add(user_id)
    return grouped


def _signups_by_day(db) -> dict[date, set]:
    rows = db.execute(select(func.date(Profile.created_at), Profile.id)).all()

    grouped: dict[date, set] = {}
    for day, user_id in rows:
        grouped.setdefault(day, set()).add(user_id)
    return grouped


def _signups_since(db, since: date) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(Profile).where(func.date(Profile.created_at) >= since)
        )
        or 0
    )


def _distinct_users(db, model, *conditions) -> int:
    statement = select(func.count(distinct(model.user_id)))
    if conditions:
        statement = statement.where(*conditions)
    return db.scalar(statement) or 0
