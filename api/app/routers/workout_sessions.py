from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser, DbSession
from app.models import Exercise, SetLog, WorkoutSession
from app.schemas.workout import (
    PersonalRecordOut,
    SetOut,
    WorkoutSessionCreate,
    WorkoutSessionOut,
    WorkoutSessionSaved,
)
from app.services import prs

router = APIRouter(prefix="/workout-sessions", tags=["workouts"])

MAX_RANGE_DAYS = 400


def _serialise(session: WorkoutSession) -> WorkoutSessionOut:
    return WorkoutSessionOut(
        id=session.id,
        client_uuid=session.client_uuid,
        session_date=session.session_date,
        split=session.split,
        notes=session.notes,
        sets=[SetOut.model_validate(s) for s in session.sets],
    )


@router.post("", response_model=WorkoutSessionSaved, status_code=status.HTTP_201_CREATED)
def create_session(
    body: WorkoutSessionCreate, user: CurrentUser, db: DbSession, response: Response
) -> WorkoutSessionSaved:
    """Save a session and report any PRs it set (spec §6).

    Idempotent on `client_uuid`: the offline queue (§8) retries writes whose
    responses were lost, and a duplicated session would corrupt both volume and
    PR history. A repeat POST returns 200 with the already-stored resource
    rather than creating a second one.

    PRs are computed against history *strictly before* this session, so a
    re-sent request cannot report the session beating itself.
    """
    existing = db.scalar(
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.sets))
        .where(WorkoutSession.client_uuid == body.client_uuid)
    )
    if existing is not None:
        if existing.user_id != user.id:
            # Someone else's idempotency key. Say nothing about it existing.
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not yours")
        # Already stored — replaying the save must not re-announce the PRs, or
        # a flaky connection would celebrate the same lift repeatedly.
        response.status_code = status.HTTP_200_OK
        return WorkoutSessionSaved(session=_serialise(existing), prs=[])

    exercise_ids = {s.exercise_id for s in body.sets}
    if exercise_ids:
        known = set(
            db.scalars(
                select(Exercise.id).where(
                    Exercise.id.in_(exercise_ids),
                    (Exercise.created_by.is_(None)) | (Exercise.created_by == user.id),
                )
            )
        )
        missing = exercise_ids - known
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown exercise id(s): {sorted(missing)}",
            )

    historical_best = _best_e1rm_before(db, user.id, exercise_ids)

    session = WorkoutSession(
        client_uuid=body.client_uuid,
        user_id=user.id,
        session_date=body.session_date,
        split=body.split,
        notes=body.notes,
        sets=[
            SetLog(
                exercise_id=s.exercise_id,
                set_number=s.set_number,
                weight_kg=s.weight_kg,
                reps=s.reps,
            )
            for s in body.sets
        ],
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    records = prs.detect(
        [
            prs.SetPerformance(exercise_id=s.exercise_id, weight_kg=float(s.weight_kg), reps=s.reps)
            for s in body.sets
        ],
        historical_best,
    )

    names = (
        dict(
            db.execute(
                select(Exercise.id, Exercise.name).where(
                    Exercise.id.in_([r.exercise_id for r in records])
                )
            ).all()
        )
        if records
        else {}
    )

    return WorkoutSessionSaved(
        session=_serialise(session),
        prs=[
            PersonalRecordOut(
                exercise_id=r.exercise_id,
                exercise_name=names.get(r.exercise_id, "Exercise"),
                e1rm=round(r.e1rm, 2),
                previous_e1rm=round(r.previous_e1rm, 2),
            )
            for r in records
        ],
    )


def _best_e1rm_before(db, user_id, exercise_ids: set[int]) -> dict[int, float]:
    """Best estimated 1RM per exercise across everything already stored.

    Computed in SQL so a long training history does not have to be pulled into
    memory on every save. The rep cap from §7.3 is applied with `least()` to
    match `prs.epley_e1rm` exactly — the two must not drift apart.
    """
    if not exercise_ids:
        return {}

    capped_reps = func.least(SetLog.reps, prs.EPLEY_REP_CAP)
    e1rm = SetLog.weight_kg * (1 + capped_reps / 30.0)

    rows = db.execute(
        select(SetLog.exercise_id, func.max(e1rm))
        .join(WorkoutSession, WorkoutSession.id == SetLog.session_id)
        .where(
            WorkoutSession.user_id == user_id,
            SetLog.exercise_id.in_(exercise_ids),
        )
        .group_by(SetLog.exercise_id)
    ).all()

    return {exercise_id: float(best) for exercise_id, best in rows}


@router.get("", response_model=list[WorkoutSessionOut])
def list_sessions(
    user: CurrentUser,
    db: DbSession,
    from_: date = Query(alias="from"),
    to: date = Query(),
) -> list[WorkoutSessionOut]:
    if to < from_:
        raise HTTPException(status_code=422, detail="`to` must not be earlier than `from`")
    if (to - from_).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"Range must not exceed {MAX_RANGE_DAYS} days")

    sessions = db.scalars(
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.sets))
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.session_date >= from_,
            WorkoutSession.session_date <= to,
        )
        .order_by(WorkoutSession.session_date.desc(), WorkoutSession.id.desc())
    ).all()

    return [_serialise(s) for s in sessions]
