from fastapi import APIRouter

from app.core.auth import CurrentUser
from app.schemas.health import AuthHealth, Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    """Unauthenticated liveness probe."""
    return Health(status="ok")


@router.get("/health-auth", response_model=AuthHealth)
def health_auth(user: CurrentUser) -> AuthHealth:
    """Proves the full chain: app session -> JWT -> verified user -> profiles row."""
    return AuthHealth(status="ok", user_id=user.id, unit=user.unit)
