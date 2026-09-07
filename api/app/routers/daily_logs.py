from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.auth import DbSession
from app.core.limits import ReadUser, WriteUser
from app.models import DailyLog
from app.schemas.daily_log import DailyLogOut, DailyLogUpsert

router = APIRouter(prefix="/daily-logs", tags=["daily-logs"])

#: A range wider than this is never what a chart needs and is cheap to refuse.
MAX_RANGE_DAYS = 400


@router.put("/{log_date}", response_model=DailyLogOut)
def upsert_daily_log(
    log_date: date, body: DailyLogUpsert, user: WriteUser, db: DbSession
) -> DailyLog:
    """Merge the provided fields into the user's row for that date (spec §6).

    Only keys actually present in the request body are written, so the weight
    tab writing `weight_kg` cannot blank out macros the nutrition tab wrote
    earlier the same day. A single INSERT ... ON CONFLICT does the whole thing,
    which keeps it safe under the retries the offline queue (§8) will make.
    """
    provided = body.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(
            status_code=422,
            detail="No fields to update",
        )

    statement = (
        pg_insert(DailyLog)
        .values(user_id=user.id, log_date=log_date, **provided)
        .on_conflict_do_update(
            index_elements=["user_id", "log_date"],
            set_=provided,
        )
        .returning(DailyLog)
    )
    row = db.scalar(statement)
    db.commit()
    return row


@router.get("", response_model=list[DailyLogOut])
def list_daily_logs(
    user: ReadUser,
    db: DbSession,
    from_: date = Query(alias="from"),
    to: date = Query(),
) -> list[DailyLog]:
    """Every log in an inclusive date range, oldest first."""
    if to < from_:
        raise HTTPException(
            status_code=422,
            detail="`to` must not be earlier than `from`",
        )
    if (to - from_).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Range must not exceed {MAX_RANGE_DAYS} days",
        )

    return list(
        db.scalars(
            select(DailyLog)
            .where(
                DailyLog.user_id == user.id,
                DailyLog.log_date >= from_,
                DailyLog.log_date <= to,
            )
            .order_by(DailyLog.log_date)
        )
    )
