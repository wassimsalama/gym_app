"""Stateless authentication.

The API never mints or stores sessions. Every request carries a Supabase-issued
access token; we verify its signature against the project's *public* keys and
trust `sub` as the user id.

Supabase signs access tokens asymmetrically (ES256 by default) and publishes
the public half as a JWKS. The API therefore holds nothing that could forge a
token — a leaked backend environment cannot be used to impersonate a user.
"""

import uuid
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.certs import default_ssl_context
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import Profile

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache
def get_jwks_client(jwks_url: str, lifespan: int) -> PyJWKClient:
    """One long-lived client per URL.

    It caches keys in-process and refetches when a token names a `kid` it has
    not seen, so key rotation needs no redeploy. Cached by URL so tests can
    point at their own JWKS without leaking state between cases.
    """
    return PyJWKClient(
        jwks_url,
        cache_keys=True,
        lifespan=lifespan,
        ssl_context=default_ssl_context(),
    )


def decode_token(token: str, settings: Settings) -> dict:
    """Verify signature, expiry and audience. Raises HTTPException on any failure."""
    client = get_jwks_client(settings.jwks_url, settings.jwks_cache_seconds)

    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except jwt.PyJWKClientError as exc:
        # Unknown `kid`, or a JWKS that could not be fetched or parsed.
        raise _unauthorized("Invalid token") from exc
    except jwt.DecodeError as exc:
        raise _unauthorized("Invalid token") from exc

    try:
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.jwt_algorithms,
            audience=settings.jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        # Deliberately opaque: never echo parser internals back to the client.
        raise _unauthorized("Invalid token") from exc


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> uuid.UUID:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    claims = decode_token(credentials.credentials, settings)
    try:
        return uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise _unauthorized("Invalid token subject") from exc


def get_current_user(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> Profile:
    """Resolve the caller's profile, creating it on first authenticated request.

    Supabase owns the identity; `profiles` is our local projection of it, so the
    row is materialised lazily rather than via an auth webhook.
    """
    profile = db.get(Profile, user_id)
    if profile is not None:
        return profile

    db.execute(pg_insert(Profile).values(id=user_id).on_conflict_do_nothing(index_elements=["id"]))
    db.commit()
    profile = db.scalar(select(Profile).where(Profile.id == user_id))
    if profile is None:  # pragma: no cover — only reachable if the insert vanished
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not materialise profile",
        )
    return profile


CurrentUser = Annotated[Profile, Depends(get_current_user)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
DbSession = Annotated[Session, Depends(get_db)]
