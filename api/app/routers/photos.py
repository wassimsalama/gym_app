from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core import storage
from app.core.auth import DbSession
from app.core.limits import ReadUser, WriteUser
from app.models import Photo
from app.schemas.photo import PhotoConfirm, PhotoOut, PresignRequest, PresignResponse

router = APIRouter(prefix="/photos", tags=["photos"])


@router.post("/presign", response_model=PresignResponse)
def presign(body: PresignRequest, user: WriteUser) -> PresignResponse:
    """Mint a short-lived upload URL (spec §6, §9).

    The key is generated here rather than accepted from the client, so a caller
    cannot aim an upload at another user's prefix.
    """
    storage.require_configured()

    key = storage.build_key(user.id)
    return PresignResponse(
        upload_url=storage.presign_upload(key, body.content_type),
        s3_key=key,
    )


@router.post("", response_model=PhotoOut, status_code=status.HTTP_201_CREATED)
def confirm(body: PhotoConfirm, user: WriteUser, db: DbSession) -> PhotoOut:
    """Record a photo the app has already uploaded.

    Idempotent on `s3_key` (§8.3): the confirm call is a queued write, and a
    retry must not produce two rows pointing at one object.
    """
    storage.require_configured()

    if not storage.owns_key(user.id, body.s3_key):
        # Someone else's prefix, or not a key this API ever issued. 404, not
        # 403 — see the note in workout_sessions.create_session.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    existing = db.scalar(select(Photo).where(Photo.user_id == user.id, Photo.s3_key == body.s3_key))
    if existing is not None:
        return _serialise(existing)

    photo = Photo(user_id=user.id, taken_on=body.taken_on, s3_key=body.s3_key)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return _serialise(photo)


@router.get("", response_model=list[PhotoOut])
def list_photos(
    user: ReadUser,
    db: DbSession,
    year: int = Query(ge=1900, le=2200),
    month: int = Query(ge=1, le=12),
) -> list[PhotoOut]:
    """A month of photos, newest first, with fresh view URLs.

    URLs are generated per request rather than stored: they expire in an hour,
    and a persisted one would be a link to private data outliving its purpose.
    """
    storage.require_configured()

    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)

    photos = db.scalars(
        select(Photo)
        .where(Photo.user_id == user.id, Photo.taken_on >= start, Photo.taken_on < end)
        .order_by(Photo.taken_on.desc(), Photo.id.desc())
    ).all()

    return [_serialise(photo) for photo in photos]


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(photo_id: int, user: WriteUser, db: DbSession) -> None:
    """Remove the row and the object (spec §9)."""
    storage.require_configured()

    photo = db.scalar(select(Photo).where(Photo.id == photo_id, Photo.user_id == user.id))
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    key = photo.s3_key
    db.delete(photo)
    db.commit()

    # Object last: a failure here leaves an orphaned object, which is far better
    # than a row pointing at something already gone.
    storage.delete_object(key)


def _serialise(photo: Photo) -> PhotoOut:
    return PhotoOut(
        id=photo.id,
        taken_on=photo.taken_on,
        view_url=storage.presign_view(photo.s3_key),
        # v1 renders the compressed original in the grid (§9); a Lambda
        # thumbnailer is explicitly out of scope.
        thumb_url=storage.presign_view(photo.thumb_key) if photo.thumb_key else None,
    )
