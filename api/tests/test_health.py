"""Phase 0 acceptance: the app -> JWT -> API -> profiles chain.

Tokens are ES256, signed by a key the local JWKS advertises — the same shape
Supabase issues.
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile
from tests.conftest import FOREIGN_KEY, make_token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_open(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_auth_requires_a_token(client: TestClient) -> None:
    resp = client.get("/health-auth")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing bearer token"


def test_health_auth_rejects_a_token_signed_by_an_unknown_key(client: TestClient) -> None:
    """A valid-looking ES256 token whose `kid` is not in the JWKS."""
    token = make_token(key=FOREIGN_KEY, kid="not-in-the-jwks")
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_health_auth_rejects_a_forged_signature_under_a_known_kid(client: TestClient) -> None:
    """The right `kid` but the wrong private key — the signature must not verify."""
    token = make_token(key=FOREIGN_KEY)
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_health_auth_rejects_a_token_with_no_kid(client: TestClient) -> None:
    token = make_token(kid=None)
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_health_auth_rejects_an_expired_token(client: TestClient) -> None:
    token = make_token(expires_in=timedelta(seconds=-1))
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token expired"


def test_health_auth_rejects_a_wrong_audience(client: TestClient) -> None:
    token = make_token(audience="some-other-app")
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_health_auth_rejects_a_token_without_a_subject(client: TestClient) -> None:
    token = make_token(include_sub=False)
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_health_auth_rejects_an_unsigned_token(client: TestClient) -> None:
    """`alg: none` must never be accepted, whatever the JWKS says."""
    import jwt

    token = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated"}, None, algorithm="none")
    resp = client.get("/health-auth", headers=bearer(token))
    assert resp.status_code == 401


def test_health_auth_rejects_garbage(client: TestClient) -> None:
    resp = client.get("/health-auth", headers=bearer("not-a-jwt"))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_health_auth_accepts_a_valid_token_and_creates_the_profile(
    client: TestClient, db: Session, user_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    assert db.get(Profile, user_id) is None

    resp = client.get("/health-auth", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "user_id": str(user_id), "unit": "lb"}

    profile = db.get(Profile, user_id)
    assert profile is not None
    assert profile.unit == "lb"  # spec §5 default


def test_profile_is_created_once_not_on_every_request(
    client: TestClient, db: Session, user_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    for _ in range(3):
        assert client.get("/health-auth", headers=auth_headers).status_code == 200

    profiles = db.scalars(select(Profile).where(Profile.id == user_id)).all()
    assert len(profiles) == 1


def test_users_are_isolated_from_each_other(client: TestClient, db: Session) -> None:
    first, second = uuid.uuid4(), uuid.uuid4()

    for uid in (first, second):
        resp = client.get("/health-auth", headers=bearer(make_token(uid)))
        assert resp.json()["user_id"] == str(uid)

    assert db.get(Profile, first) is not None
    assert db.get(Profile, second) is not None
