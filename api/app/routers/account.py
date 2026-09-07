from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete

from app.core import storage
from app.core.auth import CurrentUser, DbSession
from app.models import Profile

router = APIRouter(prefix="/account", tags=["account"])

#: Typed by the user to confirm. Deliberately not "yes" — this is irreversible
#: and App Store review expects it to be deliberate (§13).
CONFIRMATION_PHRASE = "DELETE"


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: str


class DeleteAccountResponse(BaseModel):
    deleted_photos: int
    #: The API cannot remove the Supabase identity — only the app holds a
    #: session with the authority to do that. Reported so the client can
    #: finish the job and so the response never implies more than happened.
    supabase_user_pending: bool


@router.post("/delete", response_model=DeleteAccountResponse)
def delete_account(
    body: DeleteAccountRequest, user: CurrentUser, db: DbSession
) -> DeleteAccountResponse:
    """Erase the user's data (spec §10, §13).

    Order matters. Photos are purged from S3 *before* the database rows, because
    the rows are the only record of which objects exist — dropping them first
    would orphan every image beyond recovery. Everything else cascades from
    `profiles` (§5).

    App Store review requires this to be reachable in-app, and requires it to
    actually delete rather than merely deactivate.
    """
    if body.confirm != CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=422,
            detail=f"Type {CONFIRMATION_PHRASE} to confirm account deletion",
        )

    deleted_photos = 0
    if storage.is_configured():
        # A storage failure must not leave the account half-deleted, so this is
        # allowed to raise and abort before anything in the database is touched.
        deleted_photos = storage.delete_prefix(f"{user.id}/")

    # Every table with user data cascades from here (§5).
    db.execute(delete(Profile).where(Profile.id == user.id))
    db.commit()

    return DeleteAccountResponse(deleted_photos=deleted_photos, supabase_user_pending=True)
