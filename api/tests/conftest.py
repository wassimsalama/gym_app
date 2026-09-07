"""Test fixtures.

A real JWKS is served over loopback and tokens are signed with the matching
private key, so the production code path — fetch JWKS, match `kid`, verify an
ES256 signature — runs unmodified. Nothing about verification is stubbed.

The server starts and the environment is configured *before* any app import,
because the lru_cached Settings object is built during `app.core.db` import.
"""

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives.asymmetric import ec

JWKS_PATH = "/auth/v1/.well-known/jwks.json"
SIGNING_KID = "test-signing-key"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _public_jwk(private_key: ec.EllipticCurvePrivateKey, kid: str) -> dict:
    numbers = private_key.public_key().public_numbers()
    size = (private_key.curve.key_size + 7) // 8
    return {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kid": kid,
        "x": _b64u(numbers.x.to_bytes(size, "big")),
        "y": _b64u(numbers.y.to_bytes(size, "big")),
    }


# The key the JWKS advertises, and one it does not — the second stands in for a
# token signed by some other issuer.
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
FOREIGN_KEY = ec.generate_private_key(ec.SECP256R1())
JWKS = {"keys": [_public_jwk(SIGNING_KEY, SIGNING_KID)]}


class _JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's interface
        if self.path != JWKS_PATH:
            self.send_error(404)
            return
        body = json.dumps(JWKS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence per-request logging into the pytest output."""


_server = ThreadingHTTPServer(("127.0.0.1", 0), _JwksHandler)
threading.Thread(target=_server.serve_forever, daemon=True).start()
SUPABASE_URL = f"http://127.0.0.1:{_server.server_address[1]}"

from urllib.parse import urlparse, urlunparse  # noqa: E402

_dev_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://gym:gym@localhost:5432/gym")
TEST_DATABASE_URL = urlunparse(urlparse(_dev_url)._replace(path="/gym_test"))

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SUPABASE_URL"] = SUPABASE_URL

import uuid  # noqa: E402
from collections.abc import Generator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.auth import get_jwks_client  # noqa: E402
from app.core.db import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


def _ensure_test_database() -> None:
    """CREATE DATABASE gym_test if it is not there yet (needs autocommit)."""
    admin_url = urlunparse(urlparse(TEST_DATABASE_URL)._replace(path="/postgres"))
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            sa.text("select 1 from pg_database where datname = :name"),
            {"name": "gym_test"},
        )
        if not exists:
            conn.execute(sa.text("create database gym_test"))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Generator[None, None, None]:
    _ensure_test_database()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _reset_jwks_cache() -> None:
    """Keys are cached in-process; drop them so cases cannot bleed into each other."""
    get_jwks_client.cache_clear()


@pytest.fixture
def db(_schema: None) -> Generator[Session, None, None]:
    """A session bound to a transaction that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_token(
    user_id: uuid.UUID | str | None = None,
    *,
    key: ec.EllipticCurvePrivateKey = SIGNING_KEY,
    kid: str | None = SIGNING_KID,
    algorithm: str = "ES256",
    audience: str = "authenticated",
    expires_in: timedelta = timedelta(hours=1),
    include_sub: bool = True,
) -> str:
    """Mint a token shaped like a Supabase access token."""
    now = datetime.now(UTC)
    claims: dict = {
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "role": "authenticated",
    }
    if include_sub:
        claims["sub"] = str(user_id or uuid.uuid4())
    headers = {"kid": kid} if kid else None
    return jwt.encode(claims, key, algorithm=algorithm, headers=headers)


@pytest.fixture
def shared_exercise(db: Session) -> int:
    """A catalogue entry, as `scripts/seed_exercises.py` would create.

    Distinct from a user's custom exercise, which is private to its creator —
    only a shared one can appear in two users' histories.
    """
    from app.models import Exercise

    exercise = Exercise(
        name="Barbell Bench Press",
        muscle_group="chest",
        equipment="barbell",
        source="seed",
        created_by=None,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise.id


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}
