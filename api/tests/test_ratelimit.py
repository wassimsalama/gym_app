"""Rate limiting.

The limiter is exercised directly for its arithmetic, and through the app for
the parts that only matter in a request: the 429, the Retry-After header, and
who gets counted against whom.
"""

import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.limits import client_address, limit_by_address
from app.core.ratelimit import Limit, SlidingWindowLimiter, limiter

ONE_MINUTE = Limit(max_requests=3, window_seconds=60)


@pytest.fixture(autouse=True)
def _clean_limiter():
    limiter.reset()
    yield
    limiter.reset()


# --- the window ------------------------------------------------------------


def test_requests_under_the_limit_are_allowed() -> None:
    window = SlidingWindowLimiter()
    for i in range(3):
        decision = window.check("k", ONE_MINUTE, now=100.0 + i)
        assert decision.allowed is True


def test_remaining_counts_down() -> None:
    window = SlidingWindowLimiter()
    assert window.check("k", ONE_MINUTE, now=100.0).remaining == 2
    assert window.check("k", ONE_MINUTE, now=101.0).remaining == 1
    assert window.check("k", ONE_MINUTE, now=102.0).remaining == 0


def test_exceeding_the_limit_is_refused() -> None:
    window = SlidingWindowLimiter()
    for i in range(3):
        window.check("k", ONE_MINUTE, now=100.0 + i)

    refused = window.check("k", ONE_MINUTE, now=103.0)
    assert refused.allowed is False
    assert refused.retry_after > 0


def test_the_window_slides_rather_than_resetting() -> None:
    """Slots free one at a time as individual hits age out.

    A fixed window would instead hand back the entire allowance at a boundary,
    letting a caller spend it twice over in quick succession — double the
    intended rate at exactly the wrong moment.

    Hits are placed at 100, 101 and 102 with a 60-second window, so they expire
    at 160, 161 and 162 respectively.
    """
    window = SlidingWindowLimiter()
    for i in range(3):
        window.check("k", ONE_MINUTE, now=100.0 + i)

    # Nothing has aged out yet.
    assert window.check("k", ONE_MINUTE, now=130.0).allowed is False
    assert window.check("k", ONE_MINUTE, now=159.9).allowed is False

    # The 100 hit expires, freeing exactly one slot, which this takes.
    assert window.check("k", ONE_MINUTE, now=160.5).allowed is True
    # The 101 hit expires, freeing one more.
    assert window.check("k", ONE_MINUTE, now=161.5).allowed is True
    # Nothing further has expired, so the window is full again.
    assert window.check("k", ONE_MINUTE, now=161.6).allowed is False


def test_retry_after_points_at_when_a_slot_frees() -> None:
    window = SlidingWindowLimiter()
    for i in range(3):
        window.check("k", ONE_MINUTE, now=100.0 + i)

    refused = window.check("k", ONE_MINUTE, now=110.0)
    # Oldest hit was at 100 and ages out at 160, i.e. 50s away.
    assert 45 <= refused.retry_after <= 55


def test_keys_are_independent() -> None:
    window = SlidingWindowLimiter()
    for i in range(3):
        window.check("alice", ONE_MINUTE, now=100.0 + i)

    assert window.check("alice", ONE_MINUTE, now=104.0).allowed is False
    assert window.check("bob", ONE_MINUTE, now=104.0).allowed is True


def test_idle_keys_are_swept() -> None:
    """Memory must not grow with every address that ever called."""
    window = SlidingWindowLimiter()
    for i in range(600):
        window.check(f"key-{i}", ONE_MINUTE, now=100.0)
    before = window.tracked_keys

    # Far past the TTL; the next call triggers a sweep.
    for i in range(600):
        window.check(f"later-{i}", ONE_MINUTE, now=100_000.0)

    assert window.tracked_keys < before + 600


# --- through the app -------------------------------------------------------


def app_with_limit(per_hour: int) -> TestClient:
    """A tiny app carrying only the address limit, so the numbers are legible."""
    api = FastAPI(dependencies=[__import__("fastapi").Depends(limit_by_address)])

    @api.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    def settings() -> Settings:
        return Settings(rate_limit_enabled=True, rate_limit_ip_per_hour=per_hour)

    api.dependency_overrides[get_settings] = settings
    get_settings.cache_clear()
    return TestClient(api)


def test_the_limit_returns_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_IP_PER_HOUR", "3")
    get_settings.cache_clear()

    client = app_with_limit(3)
    for _ in range(3):
        assert client.get("/ping").status_code == 200

    refused = client.get("/ping")
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0
    assert "Too many requests" in refused.json()["detail"]

    get_settings.cache_clear()


def test_disabling_it_lets_everything_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    client = app_with_limit(1)
    for _ in range(10):
        assert client.get("/ping").status_code == 200

    get_settings.cache_clear()


# --- who gets counted ------------------------------------------------------


def make_request(headers: dict[str, str], host: str = "10.1.2.3") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (host, 1234),
        }
    )


def test_the_socket_address_is_used_by_default() -> None:
    """Trusting X-Forwarded-For with no proxy in front would hand every client
    an unlimited supply of fresh identities."""
    settings = Settings(trust_proxy_headers=False)
    request = make_request({"x-forwarded-for": "1.2.3.4"})

    assert client_address(request, settings) == "10.1.2.3"


def test_the_forwarded_address_is_used_behind_a_proxy() -> None:
    settings = Settings(trust_proxy_headers=True)
    request = make_request({"x-forwarded-for": "1.2.3.4"})

    assert client_address(request, settings) == "1.2.3.4"


def test_the_original_client_is_taken_from_a_proxy_chain() -> None:
    settings = Settings(trust_proxy_headers=True)
    request = make_request({"x-forwarded-for": "1.2.3.4, 70.41.3.18, 150.172.238.178"})

    assert client_address(request, settings) == "1.2.3.4"


def test_a_missing_header_behind_a_proxy_falls_back() -> None:
    settings = Settings(trust_proxy_headers=True)
    assert client_address(make_request({}), settings) == "10.1.2.3"


def test_users_are_limited_separately(client: TestClient) -> None:
    """One heavy user must not lock everyone else out."""
    from tests.conftest import make_token

    first = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    second = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}

    limiter.reset()
    assert client.get("/health-auth", headers=first).status_code == 200
    assert client.get("/health-auth", headers=second).status_code == 200
