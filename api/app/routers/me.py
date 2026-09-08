from fastapi import APIRouter

from app.core.auth import DbSession
from app.core.limits import WriteUser
from app.schemas.health import AuthHealth
from app.schemas.profile import ProfileUpdate

router = APIRouter(tags=["profile"])


@router.patch("/me", response_model=AuthHealth)
def update_me(body: ProfileUpdate, user: WriteUser, db: DbSession) -> AuthHealth:
    """Change the caller's display unit.

    Returns the same shape as /health-auth deliberately: that is where the app
    already reads the profile from, and one representation of "who am I" is
    easier to keep honest than two that can drift.

    There is no user id in the request. The row updated is the one the verified
    token resolved to, which is what makes this endpoint uninteresting to attack.
    """
    user.unit = body.unit
    db.commit()
    db.refresh(user)

    return AuthHealth(status="ok", user_id=user.id, unit=user.unit)
