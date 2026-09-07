from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select

from app.core.auth import DbSession
from app.core.limits import ReadUser, WriteUser
from app.models import Exercise, SetLog, WorkoutSession
from app.schemas.workout import ExerciseCreate, ExerciseOut, LastSets, SetOut

router = APIRouter(prefix="/exercises", tags=["exercises"])

#: Spec §6 — the search bar shows this many.
SEARCH_LIMIT = 20


def _visible_to(user_id) -> Select[tuple[Exercise]]:
    """Seeded exercises plus the caller's own. Never another user's customs."""
    return select(Exercise).where(
        or_(Exercise.created_by.is_(None), Exercise.created_by == user_id)
    )


@router.get("", response_model=list[ExerciseOut])
def search_exercises(
    user: ReadUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=100),
) -> list[Exercise]:
    """Top matches for the session builder's search bar.

    Uses the GIN full-text index for word matching, plus a prefix match so
    typing "benc" finds something before the word is complete — `to_tsquery`
    alone would not. Results put the user's own exercises first, since a custom
    entry exists precisely because the catalogue was missing something.
    """
    statement = _visible_to(user.id)

    if q and q.strip():
        term = q.strip()
        statement = statement.where(
            or_(
                func.to_tsvector("simple", Exercise.name).op("@@")(
                    func.plainto_tsquery("simple", term)
                ),
                Exercise.name.ilike(f"%{term}%"),
            )
        )

    return list(
        db.scalars(
            statement.order_by(
                # Custom first, then alphabetical.
                Exercise.created_by.is_(None),
                Exercise.name,
            ).limit(SEARCH_LIMIT)
        )
    )


@router.post("", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED)
def create_exercise(body: ExerciseCreate, user: WriteUser, db: DbSession) -> Exercise:
    """Create a custom exercise when the search misses (spec §2.3)."""
    name = body.name.strip()

    existing = db.scalar(_visible_to(user.id).where(func.lower(Exercise.name) == name.lower()))
    if existing is not None:
        # Idempotent by name: the app retries writes (§8), and a duplicate
        # catalogue entry would split the user's history for that lift in two.
        return existing

    exercise = Exercise(
        name=name,
        muscle_group=body.muscle_group,
        equipment=(body.equipment or "").strip() or None,
        source="custom",
        created_by=user.id,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


@router.get("/{exercise_id}/last-sets", response_model=LastSets)
def last_sets(exercise_id: int, user: ReadUser, db: DbSession) -> LastSets:
    """Sets from the user's most recent session containing this exercise.

    This is the prefill behind §2.3's "logging an unchanged session is ~3 taps".
    An exercise never performed returns an empty list rather than a 404 — the
    app wants to show a blank first set, not an error.
    """
    exercise = db.scalar(_visible_to(user.id).where(Exercise.id == exercise_id))
    if exercise is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")

    latest = db.execute(
        select(WorkoutSession.id, WorkoutSession.session_date)
        .join(SetLog, SetLog.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user.id, SetLog.exercise_id == exercise_id)
        .order_by(WorkoutSession.session_date.desc(), WorkoutSession.id.desc())
        .limit(1)
    ).first()

    if latest is None:
        return LastSets(exercise_id=exercise_id, session_date=None, sets=[])

    session_id, session_date = latest
    sets = db.scalars(
        select(SetLog)
        .where(SetLog.session_id == session_id, SetLog.exercise_id == exercise_id)
        .order_by(SetLog.set_number)
    ).all()

    return LastSets(
        exercise_id=exercise_id,
        session_date=session_date,
        sets=[SetOut.model_validate(s) for s in sets],
    )
