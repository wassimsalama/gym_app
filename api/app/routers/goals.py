from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.core.auth import DbSession
from app.core.limits import ReadUser, WriteUser
from app.models import DailyLog, Goal
from app.schemas.goal import GoalCreate, GoalOut, GoalUpdate

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalCreate, user: WriteUser, db: DbSession) -> Goal:
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
def get_active_goal(user: ReadUser, db: DbSession) -> Goal:
    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .limit(1)
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active goal")
    return goal


@router.patch("/active", response_model=GoalOut)
def update_active_goal(body: GoalUpdate, user: WriteUser, db: DbSession) -> Goal:
    """Change the goal already in flight.

    The destination moves, and so may the baseline: a mistyped starting weight
    used to be fixable only by starting a new goal, which discarded the goal's
    history to correct a number that was never right (DECISION 1(a), a §7.1
    deviation recorded in DECISIONS.md).

    `start_date` is still untouched. Moving it changes which observations count
    toward the trend, which is re-baselining, and that is `POST /goals`.

    Progress and the projection are derived at read time from these two numbers,
    so correcting the baseline recalculates both with no extra work here.
    """
    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .limit(1)
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active goal")

    provided = body.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(status_code=422, detail="No fields to update")

    for field, value in provided.items():
        setattr(goal, field, value)

    db.commit()
    db.refresh(goal)
    return goal
