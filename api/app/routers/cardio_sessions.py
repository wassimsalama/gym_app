from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.core.auth import DbSession
from app.core.limits import ReadUser, WriteUser
from app.models import CardioSession
from app.schemas.cardio import CardioSessionCreate, CardioSessionOut

router = APIRouter(prefix="/cardio-sessions", tags=["cardio"])

#: Same ceiling as workout sessions and daily logs — an unbounded range is an
#: unbounded query.
MAX_RANGE_DAYS = 400


@router.post("", response_model=CardioSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    body: CardioSessionCreate, user: WriteUser, db: DbSession, response: Response
) -> CardioSession:
    """Save a cardio session.

    Idempotent on `client_uuid`, like workout sessions: the offline queue (§8)
    retries writes whose responses were lost, and a duplicate would overstate
    activity. A repeat POST returns 200 with the stored row.
    """
    existing = db.scalar(select(CardioSession).where(CardioSession.client_uuid == body.client_uuid))
    if existing is not None:
        if existing.user_id != user.id:
            # Someone else's idempotency key. 404 rather than 403 — a 403 would
            # confirm the key is in use, which is what must not be revealed.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        response.status_code = status.HTTP_200_OK
        return existing

    session = CardioSession(user_id=user.id, **body.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=list[CardioSessionOut])
def list_sessions(
    user: ReadUser,
    db: DbSession,
    from_: date = Query(alias="from"),
    to: date = Query(),
) -> list[CardioSession]:
    if to < from_:
        raise HTTPException(status_code=422, detail="`to` must not be earlier than `from`")
    if (to - from_).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"Range must not exceed {MAX_RANGE_DAYS} days")

    return list(
        db.scalars(
            select(CardioSession)
            .where(
                CardioSession.user_id == user.id,
                CardioSession.session_date >= from_,
                CardioSession.session_date <= to,
            )
            .order_by(CardioSession.session_date.desc(), CardioSession.id.desc())
        )
    )
