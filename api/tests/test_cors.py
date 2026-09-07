"""CORS.

Irrelevant on native and mandatory on the web — the browser refuses every call
before it is sent, and the client can only report a network failure. Worth
pinning so it cannot regress into an afternoon of debugging the wrong thing.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings

ALLOWED = [
    "http://localhost:8081",
    "http://localhost:19006",
    "http://127.0.0.1:8081",
    "http://192.168.1.25:8000",
    "http://10.0.0.5:3000",
    "http://172.16.4.2:8080",
]

REFUSED = [
    "https://evil.example.com",
    "http://notlocalhost.com",
    "http://localhost.evil.com",
    "https://192.168.1.25.evil.com",
]


def preflight(client: TestClient, origin: str):
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


@pytest.mark.parametrize("origin", ALLOWED)
def test_development_origins_are_allowed(client: TestClient, origin: str) -> None:
    response = preflight(client, origin)
    assert response.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", REFUSED)
def test_public_origins_are_refused(client: TestClient, origin: str) -> None:
    """A browser blocks the call when the header is absent — which is the point."""
    response = preflight(client, origin)
    assert "access-control-allow-origin" not in response.headers


def test_a_simple_request_carries_the_header_too(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:8081"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8081"


def test_retry_after_is_readable_by_the_browser(client: TestClient) -> None:
    """Rate limiting is useless to the client if it cannot read the header."""
    response = preflight(client, "http://localhost:8081")
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "Retry-After" in exposed or response.status_code == 200

    simple = client.get("/health", headers={"Origin": "http://localhost:8081"})
    assert "Retry-After" in simple.headers.get("access-control-expose-headers", "")


def test_configuring_origins_switches_off_the_development_fallback() -> None:
    """Production sets an explicit list; localhost must then stop being special."""
    configured = Settings(allowed_origins="https://gym.example.com")

    assert configured.origins == ["https://gym.example.com"]
    assert configured.dev_origin_regex is None


def test_an_unset_list_enables_the_development_fallback() -> None:
    assert Settings(allowed_origins="").dev_origin_regex is not None


def test_multiple_production_origins_are_parsed() -> None:
    configured = Settings(allowed_origins="https://gym.example.com, https://www.gym.example.com")
    assert configured.origins == ["https://gym.example.com", "https://www.gym.example.com"]
