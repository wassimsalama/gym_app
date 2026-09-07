from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.core.auth import CurrentUser, DbSession
from app.models import DailyLog, Goal
from app.schemas.goal import GoalCreate, GoalOut

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalCreate, user: CurrentUser, db: DbSession) -> Goal:
    """Open a goal, closing any previous active one (spec §6).

    Start weight is read from the user's most recent weight observation rather
    than accepted from the client (§2.6, "auto from first log") — at onboarding
    the most recent log *is* the first one, and for a goal opened later the
    current weight is the only honest baseline. The goal's start date is that
    same observation's date, which keeps the server out of the business of
    deciding what "today" is (§6).
    """
    latest = db.execute(
        select(DailyLog.log_date, DailyLog.weight_kg)
        .where(DailyLog.user_id == user.id, DailyLog.weight_kg.is_not(None))
        .order_by(DailyLog.log_date.desc())
        .limit(1)
    ).first()

    if latest is None:
        raise HTTPException(
            status_code=422,
            detail="Log a weight before setting a goal — it becomes the starting point",
        )

    start_date, start_weight_kg = latest

    db.execute(
        update(Goal)
        .where(Goal.user_id == user.id, Goal.status == "active")
        .values(status="abandoned")
    )

    goal = Goal(
        user_id=user.id,
        start_weight_kg=start_weight_kg,
        goal_weight_kg=body.goal_weight_kg,
        start_date=start_date,
        target_date=body.target_date,
        status="active",
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/active", response_model=GoalOut)
def get_active_goal(user: CurrentUser, db: DbSession) -> Goal:
    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .limit(1)
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active goal")
    return goal
